"""The content of a draft and the rules for changing it.

A draft is a set of *fields* (the header and signature block of the document, one box each) and an ordered list of *blocks* (the
body). Every piece records who owns it, because the assistant and the person drafting edit the same page:

* ``system``    — filled by the application (quốc hiệu, tên cơ quan from the drafting unit); only the user may override it
* ``assistant`` — written by the assistant; either side may edit it
* ``user``      — written by the user (or left for them to fill); the assistant may fill a blank one but never overwrites it

The assistant cannot rewrite what a person wrote. It *proposes* a change to a block, and the person accepts or rejects it.

Blocks are ``heading`` (a roman section or the title of a khoản, bold), ``para``, ``item`` (a "-", "+" or "a)" line), ``table``
(its spec in ``table``, see `tables`) and ``appendix`` (the title of a phụ lục; the blocks after it, up to the next appendix,
belong to it). Text is stored plain: emphasis follows from the kind, as Thông tư 68 assigns it to each numbering level.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.core.errors import ValidationFailed

from . import tables, templates
from .markup import clean, item_text, kind_for

OWNERS = ("system", "assistant", "user")
BLOCK_KINDS = ("heading", "para", "item", "table", "appendix")
MAX_BLOCKS = 400
MAX_TEXT = 20_000
HISTORY_KEEP = 60
_WORDS = re.compile(r"\w", re.UNICODE)
FIXED_TEXT = {"quoc_hieu": "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", "tieu_ngu": "Độc lập - Tự do - Hạnh phúc"}
DEFAULT_NOI_NHAN = "- Lưu: VT, …. …."  # "Lưu: VT, <drafting office>. <drafter's initials><copies>."
NHU_TREN = "- Như trên;"
_LUU_LINE = re.compile(r"^(\s*-\s*Lưu\s*:\s*VT\b[^.\n]*\.)[ \t]*(.*)$", re.IGNORECASE | re.MULTILINE)
_APPENDIX_WORD = re.compile(r"^\s*phụ\s+lục(?:\s+[IVXLC\d]+)?\s*[:.\-–]?\s*", re.IGNORECASE)
_ROMAN = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV")


def blank(text: str) -> bool:
    """Whether `text` has no words (empty, or only the dots and punctuation left from a form)."""
    return not _WORDS.search(text or "")


def with_nhu_tren(noi_nhan: str) -> str:
    """Opens the "Nơi nhận" list with "- Như trên;".

    Thông tư 68: a công văn lists its "Kính gửi" addressees in "Nơi nhận" as "Như trên".

    Args:
        noi_nhan: The list, one recipient per line.

    Returns:
        The list unchanged when it already has "Như trên", else with "- Như trên;" as its first line (blank lines dropped).
    """
    lines = [line for line in (noi_nhan or "").splitlines() if line.strip()]
    if any("như trên" in line.casefold() for line in lines):
        return noi_nhan
    return "\n".join([NHU_TREN, *lines])


def luu_left_open(noi_nhan: str) -> str:
    """Blanks what follows the drafting office on the "Lưu" line.

    Only the drafter knows their initials and the number of copies, so what the assistant writes there is replaced by "…".

    Args:
        noi_nhan: The "Nơi nhận" list.

    Returns:
        The list with "- Lưu: VT, CNTT. Th03." turned into "- Lưu: VT, CNTT. …."; other lines unchanged.
    """
    return _LUU_LINE.sub(lambda m: f"{m.group(1)} …." if _WORDS.search(m.group(2)) else m.group(0), noi_nhan)


def with_luu(noi_nhan: str, luu_line: str) -> str:
    """Replaces the "Lưu" line of the "Nơi nhận" list.

    Args:
        noi_nhan: The list.
        luu_line: The new "Lưu" line (see `Issuer.luu_line`).

    Returns:
        The list with its first "Lưu" line replaced, or with `luu_line` added at the end when it has none.
    """
    if _LUU_LINE.search(noi_nhan or ""):
        return _LUU_LINE.sub(lambda _: luu_line, noi_nhan, count=1)
    return "\n".join(line for line in ((noi_nhan or "").rstrip(), luu_line) if line)


def luu_open(noi_nhan: str) -> bool:
    """Whether the "Lưu" line still waits for the drafting office, the drafter's initials or the number of copies."""
    return any("…" in m.group(0) for m in _LUU_LINE.finditer(noi_nhan or ""))


@dataclass
class Issuer:
    """The unit issuing a document, as its header prints it, and what its documents usually carry.

    Attributes:
        name: The issuing body ("Bộ Tham mưu").
        parent: Its superior, printed above it ("Quân khu 3").
        symbol: The number symbol without the number ("TM-KHQS", "KH-TM"); empty when unknown.
        luu: Abbreviation of the drafting office on the "Lưu" line ("KHQS").
        signer: The usual authority and title of the signer, one per line ("KT. THAM MƯU TRƯỞNG\\nPHÓ THAM MƯU TRƯỞNG").
    """

    name: str = ""
    parent: str = ""
    symbol: str = ""
    luu: str = ""
    signer: str = ""

    def number_line(self, kind: str) -> str:
        """The "Số" line before the registry clerk numbers the document.

        Args:
            kind: Kind symbol of the document ("CV", "KH", ...).

        Returns:
            "Số: …/TM-KHQS"; the parts of the symbol that are unknown are "…".
        """
        return f"Số: …/{self.symbol or ('…-…' if kind == 'CV' else f'{kind}-…')}"

    def luu_line(self) -> str:
        """The last line of "Nơi nhận": "- Lưu: VT, KHQS. …." (drafting office, then the drafter's initials and copies)."""
        return f"- Lưu: VT, {self.luu}. …." if self.luu else DEFAULT_NOI_NHAN


@dataclass
class Appendix:
    """One phụ lục of a draft.

    Attributes:
        label: "Phụ lục", or "Phụ lục II" when the draft has several (Thông tư 68 Mẫu 15a numbers them in roman).
        block: The ``appendix`` block, whose text is the title.
        blocks: The blocks that belong to the appendix.
    """

    label: str
    block: dict[str, Any]
    blocks: list[dict[str, Any]]

    @property
    def landscape(self) -> bool:
        """Whether the appendix prints landscape: one of its tables is too wide for portrait (see `tables.landscape`)."""
        return any(tables.landscape(b["table"]) for b in self.blocks if b["kind"] == "table" and b.get("table"))


def split(blocks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[Appendix]]:
    """Separates the body of a draft from its appendices.

    Args:
        blocks: The blocks of the draft, in order.

    Returns:
        ``(body blocks before the first appendix, appendices in order)``.
    """
    starts = [i for i, b in enumerate(blocks) if b["kind"] == "appendix"]
    if not starts:
        return list(blocks), []
    numbered = len(starts) > 1
    out = []
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(blocks)
        label = f"Phụ lục {_ROMAN[n] if n < len(_ROMAN) else n + 1}" if numbered else "Phụ lục"
        out.append(Appendix(label, blocks[start], blocks[start + 1:end]))
    return blocks[:starts[0]], out


def _loaded(block: dict[str, Any]) -> dict[str, Any]:
    """A copy of a stored block with what older drafts lack: a version, and ids on the rows and columns of its tables."""
    out = dict(block)
    out.setdefault("version", 1)
    if out.get("table"):
        out["table"] = tables.ensure_ids(out["table"])
    proposal = out.get("proposal")
    if proposal and proposal.get("table"):
        out["proposal"] = {**proposal, "table": tables.ensure_ids(proposal["table"])}
    return out


@dataclass
class DraftContent:
    """Fields and blocks of one draft with the operations that keep them consistent.

    Attributes:
        template: The kind of document.
        fields: ``{key: {"text", "owner"}}`` in the template's order.
        blocks: ``[{"id", "kind", "text", "owner", "proposal", "version", "table"?, "stale"?}]``, the body in order. ``version``
            goes up each time the block's content changes; ``stale`` marks a passage quoting figures a table no longer holds
            (``{"tables": [block ids], "figures": ["1.200", ...]}``).
        counter: The last block number handed out; ids are never reused.
    """

    template: templates.Template
    fields: dict[str, dict[str, Any]] = field(default_factory=dict)
    blocks: list[dict[str, Any]] = field(default_factory=list)
    counter: int = 0

    # ----- creation -----
    @classmethod
    def new(cls, template: templates.Template, issuer: Issuer, today: date | None = None) -> "DraftContent":
        """Creates an empty draft with the parts the application knows already filled.

        Args:
            template: The kind of document.
            issuer: The issuing unit: its names, symbol and "Lưu" office fill the header (owned by the system), its usual signer
                the authority line (owned by the assistant, so either side may change it).
            today: The date of the document; today by default.

        Returns:
            The draft, without blocks. A kind that requires "Kính gửi" starts its "Nơi nhận" with "- Như trên;".
        """
        today = today or date.today()
        out = cls(template)
        for key in template.fields:
            text, owner = "", "assistant"
            if key in FIXED_TEXT:
                text, owner = FIXED_TEXT[key], "system"
            elif key == "co_quan_chu_quan":
                text, owner = issuer.parent.upper(), "system" if issuer.parent else "user"
            elif key == "co_quan_ban_hanh":
                text, owner = issuer.name.upper(), "system" if issuer.name else "user"
            elif key == "so_ky_hieu":
                text, owner = issuer.number_line(template.kind), "system"
            elif key == "dia_danh_ngay":
                text, owner = f"……, ngày {today.day} tháng {today.month} năm {today.year}", "user"
            elif key == "ten_loai":
                text, owner = template.title_word, "system"
            elif key == "quyen_han":
                text, owner = (issuer.signer, "assistant") if issuer.signer else ("", "user")
            elif key == "nguoi_ky":
                owner = "user"
            elif key == "noi_nhan":
                text = issuer.luu_line()
                if "kinh_gui" in template.required:
                    text = with_nhu_tren(text)
            out.fields[key] = {"text": text, "owner": owner}
        return out

    @classmethod
    def load(cls, template: templates.Template, fields: dict[str, Any], blocks: list[dict[str, Any]], counter: int) -> "DraftContent":
        """Rebuilds the content from its stored form.

        Args:
            template: The kind of document.
            fields: Stored fields.
            blocks: Stored blocks.
            counter: Stored block counter.

        Returns:
            The content, holding copies of the stored dicts (see `_loaded`).
        """
        return cls(template, {k: dict(v) for k, v in fields.items()}, [_loaded(b) for b in blocks], counter)

    # ----- reading -----
    def needs_input(self, key: str) -> bool:
        """Whether a required field still waits for a person.

        Args:
            key: Field key.

        Returns:
            True when the field is required and blank, a user field with a "…" left in it, or a "Lưu" line without the drafter's
            initials.
        """
        spec = self.fields[key]
        if key not in self.template.required:
            return False
        if key == "noi_nhan" and luu_open(spec["text"]):
            return True
        return blank(spec["text"]) or (spec["owner"] == "user" and "…" in spec["text"])

    def missing(self) -> list[str]:
        """Keys of the fields that still need input, in page order."""
        return [k for k in self.template.fields if self.needs_input(k)]

    def view(self) -> dict[str, Any]:
        """The fields and blocks as the API presents them.

        Returns:
            ``{"fields", "blocks", "missing"}``. A table block also carries ``landscape`` (the page it prints on is landscape:
            only an appendix turns), ``too_wide`` (its columns cannot show their longest words on that page), ``blanks`` (cells
            still holding "…") and ``problems`` (what its formulas and sums could not work out); an appendix block carries
            ``label`` and ``landscape``.
        """
        fields = {k: {"label": templates.label_of(k), "text": v["text"], "owner": v["owner"], "needs_input": self.needs_input(k),
                      "multiline": templates.is_multiline(k)} for k, v in self.fields.items()}
        blocks = [dict(b) for b in self.blocks]
        by_id = {b["id"]: b for b in blocks}
        for b in blocks:
            if b["kind"] == "table" and b.get("table"):
                b.update(landscape=False, too_wide=not tables.fits(b["table"], tables.PORTRAIT_CM), blanks=tables.blanks(b["table"]),
                         problems=tables.problems(b["table"]))
        for appendix in split(self.blocks)[1]:
            by_id[appendix.block["id"]].update(label=appendix.label, landscape=appendix.landscape)
            room = tables.LANDSCAPE_CM if appendix.landscape else tables.PORTRAIT_CM
            for member in appendix.blocks:
                if member["kind"] == "table" and member.get("table"):
                    by_id[member["id"]].update(landscape=appendix.landscape, too_wide=not tables.fits(member["table"], room))
        return {"fields": fields, "blocks": blocks, "missing": self.missing()}

    def block(self, block_id: str) -> dict[str, Any]:
        """Finds a block.

        Args:
            block_id: Block id ("b3").

        Returns:
            The block itself (changes to it change the draft).

        Raises:
            ValidationFailed: No block has that id.
        """
        for item in self.blocks:
            if item["id"] == block_id:
                return item
        raise ValidationFailed(f"Không có đoạn '{block_id}' trong bản dự thảo.")

    # ----- fields -----
    def set_fields(self, values: dict[str, str], by: str) -> tuple[list[str], dict[str, str]]:
        """Sets fields.

        The assistant is refused a field it may not write: not part of this kind of document, filled by the application, or already
        written by the user; what it writes after the drafting office on the "Lưu" line is left as "…". The user may set any field
        of the document. Once there is a "Kính gửi", "Nơi nhận" opens with "- Như trên;" unless the user wrote it otherwise.

        Args:
            values: ``{key: text}``; Markdown marks are removed.
            by: ``assistant`` or ``user``.

        Returns:
            ``(applied keys, {refused key: reason})``.
        """
        applied: list[str] = []
        refused: dict[str, str] = {}
        for key, raw in values.items():
            text = clean(raw or "").strip()
            if key not in self.fields:
                refused[key] = f"Mẫu {self.template.name} không có ô '{key}'."
                continue
            if len(text) > MAX_TEXT:
                refused[key] = "Nội dung quá dài."
                continue
            current = self.fields[key]
            if by == "assistant":
                if current["owner"] == "system":
                    refused[key] = "Ô này do hệ thống tự điền; chỉ người dùng được đổi."
                    continue
                if current["owner"] == "user" and not (blank(current["text"]) or "…" in current["text"]):
                    refused[key] = "Ô này do người dùng nhập; không được ghi đè."
                    continue
                if key == "noi_nhan":
                    text = luu_left_open(text)
            self.fields[key] = {"text": text, "owner": by}
            applied.append(key)
        if {"kinh_gui", "noi_nhan"} & set(applied):
            self._nhu_tren(user_wrote="noi_nhan" in applied and by == "user")
        return applied, refused

    def _nhu_tren(self, *, user_wrote: bool) -> None:
        """Adds "- Như trên;" to "Nơi nhận" when there is a "Kính gửi", unless the user has just written "Nơi nhận" themselves."""
        to, noi_nhan = self.fields.get("kinh_gui"), self.fields.get("noi_nhan")
        if to is None or noi_nhan is None or blank(to["text"]) or user_wrote:
            return
        noi_nhan["text"] = with_nhu_tren(noi_nhan["text"])

    # ----- body -----
    def _new_id(self) -> str:
        """The next block id ("b1", "b2", ...)."""
        self.counter += 1
        return f"b{self.counter}"

    @staticmethod
    def _shape(kind: str, text: str, table: Any = None) -> tuple[str, str, dict[str, Any] | None]:
        """A block as it is stored.

        Args:
            kind: The kind it was written as.
            text: Its text (the title of an appendix; ignored for a table).
            table: The spec of a table block.

        Returns:
            ``(kind, text, table)``: plain text, the kind its numbering calls for (see `markup.kind_for`), a list line with its mark,
            an appendix title without a leading "Phụ lục", a normalised table spec and its summary as text.

        Raises:
            ValidationFailed: An unknown kind, an empty or overlong text, a table without a valid spec.
        """
        if kind not in BLOCK_KINDS:
            raise ValidationFailed(f"Loại đoạn '{kind}' không hợp lệ (heading, para, item, table hoặc appendix).")
        if kind == "table":
            if table is None:
                raise ValidationFailed("Đoạn loại 'table' phải có 'table' (columns, rows).")
            spec = tables.normalize(table)
            return kind, tables.summary(spec), spec
        text = clean(text or "").strip()
        if kind == "appendix":
            text = _APPENDIX_WORD.sub("", text, count=1).strip()
        if blank(text) or len(text) > MAX_TEXT:
            raise ValidationFailed("Đoạn trống hoặc quá dài.")
        kind = kind_for(kind, text)
        return kind, item_text(text) if kind == "item" else text, None

    def _make(self, kind: str, text: str, owner: str, table: Any = None) -> dict[str, Any]:
        """A new block with a fresh id (see `_shape` for what is checked)."""
        kind, text, spec = self._shape(kind, text, table)
        out = {"id": self._new_id(), "kind": kind, "text": text, "owner": owner, "proposal": None, "version": 1}
        if spec is not None:
            out["table"] = spec
        return out

    def set_content(self, items: list[dict[str, Any]], by: str = "assistant") -> list[str]:
        """Replaces the whole body.

        Args:
            items: ``[{"kind", "text", "table"?}]`` in order.
            by: ``assistant`` or ``user``; the new blocks are theirs.

        Returns:
            The new block ids.

        Raises:
            ValidationFailed: Nothing to write, too many blocks, an invalid block, or (for the assistant) a body holding blocks the
                user wrote: those are changed through proposals instead.
        """
        if not items:
            raise ValidationFailed("Nội dung trống.")
        if len(items) > MAX_BLOCKS:
            raise ValidationFailed(f"Tối đa {MAX_BLOCKS} đoạn.")
        if by == "assistant" and any(b["owner"] == "user" for b in self.blocks):
            raise ValidationFailed("Bản dự thảo có đoạn do người dùng viết; hãy dùng canvas_edit_block để đề xuất chỉnh sửa từng đoạn.")
        made = [self._make(i.get("kind", "para"), i.get("text", ""), by, i.get("table")) for i in items]
        self.blocks = made
        return [b["id"] for b in made]

    def propose(self, block_id: str, action: str, text: str = "", note: str = "", kind: str = "para",
                table: Any = None) -> dict[str, Any]:
        """Records the assistant's suggested change to the body, left for the user to accept or reject.

        Args:
            block_id: Block to replace or delete; for ``insert`` the block after which to insert ("" = at the start).
            action: ``replace``, ``delete`` or ``insert``.
            text: The new text (``replace`` and ``insert``).
            note: A short reason shown to the user.
            kind: Kind of the inserted block (``insert`` only). A replacement keeps the block's kind unless its numbering calls
                for another one.
            table: The spec of an inserted table, or the new spec of a table block being replaced.

        Returns:
            The block carrying the proposal (an inserted block has an empty text until it is accepted).

        Raises:
            ValidationFailed: An unknown action or block, an empty text, a table block replaced without a spec, or a replacement
                that changes nothing but the formatting (bold and numbering come from the kind of the block, not the text).
        """
        if action == "insert":
            index = 0 if not block_id else self.blocks.index(self.block(block_id)) + 1
            new = self._make(kind, text, "assistant", table)
            new["proposal"] = {"action": "insert", "text": new["text"], "note": note.strip()}
            if "table" in new:
                new["proposal"]["table"] = new.pop("table")
            new["text"] = ""
            self.blocks.insert(index, new)
            return new
        target = self.block(block_id)
        if action == "delete":
            target["proposal"] = {"action": "delete", "text": "", "note": note.strip()}
        elif action == "replace":
            if target["kind"] == "table":
                if table is None:
                    raise ValidationFailed("Đoạn này là bảng: gửi bảng mới trong 'table'.")
                new_kind, new_text, spec = self._shape("table", "", table)
            else:
                if blank(text) or len(text) > MAX_TEXT:
                    raise ValidationFailed("Nội dung đề xuất trống hoặc quá dài.")
                new_kind, new_text, spec = self._shape(target["kind"], text)
            if new_text == target["text"] and spec == target.get("table"):
                raise ValidationFailed("Đề xuất không đổi nội dung. In đậm, đánh số do hệ thống tự trình bày theo Thông tư 68 "
                                       "theo loại đoạn (heading/para/item); không cần đề xuất sửa định dạng.")
            target["proposal"] = {"action": "replace", "text": new_text, "note": note.strip()}
            if spec is not None:
                target["proposal"]["table"] = spec
            if new_kind != target["kind"]:
                target["proposal"]["kind"] = new_kind
        else:
            raise ValidationFailed("action phải là replace, delete hoặc insert.")
        return target

    def accept(self, block_id: str) -> str:
        """Applies the proposal on a block.

        Args:
            block_id: The block carrying the proposal.

        Returns:
            The proposal's action.

        Raises:
            ValidationFailed: Unknown block, or no proposal on it.
        """
        target = self.block(block_id)
        proposal = target.get("proposal")
        if not proposal:
            raise ValidationFailed("Đoạn này không có đề xuất nào.")
        if proposal["action"] == "delete":
            self.blocks.remove(target)
        else:
            old_table = target.get("table")
            target["text"], target["proposal"] = proposal["text"], None
            target["kind"] = proposal.get("kind", target["kind"])
            if "table" in proposal:
                target["table"] = proposal["table"]
            if proposal["action"] == "replace":
                target["version"] = target.get("version", 1) + 1
                target.pop("stale", None)
                if old_table and target.get("table"):
                    self._mark_stale(target["id"], old_table, target["table"])
            target["owner"] = "assistant" if proposal["action"] == "insert" else target["owner"]
        return proposal["action"]

    def reject(self, block_id: str) -> str:
        """Drops the proposal on a block; a proposed insertion disappears with it.

        Args:
            block_id: The block carrying the proposal.

        Returns:
            The proposal's action.

        Raises:
            ValidationFailed: Unknown block, or no proposal on it.
        """
        target = self.block(block_id)
        proposal = target.get("proposal")
        if not proposal:
            raise ValidationFailed("Đoạn này không có đề xuất nào.")
        if proposal["action"] == "insert":
            self.blocks.remove(target)
        else:
            target["proposal"] = None
        return proposal["action"]

    def edit_table(self, block_id: str, base_version: int, ops: list[dict[str, Any]], note: str = "") -> tuple[dict[str, Any], list[str]]:
        """Records the assistant's edits to a table, by row and column id, as a proposal for the user.

        The edits apply to the table as it stands, or to the table the assistant already proposed for this block, so edits made
        in several calls add up to one proposal.

        Args:
            block_id: The table block.
            base_version: The block's ``version`` the assistant read; a different one means the table changed since.
            ops: The edits (see `tables.apply`).
            note: A short reason shown to the user.

        Returns:
            ``(the block carrying the proposal, notes naming the rows and columns created or removed)``.

        Raises:
            ValidationFailed: Not a table, a stale version, a pending proposal to delete the table, edits `tables.apply` refuses,
                or edits that leave the table as it is.
        """
        target = self.block(block_id)
        if target["kind"] != "table":
            raise ValidationFailed(f"Đoạn {block_id} không phải bảng.")
        current = target.get("version", 1)
        if base_version != current:
            raise ValidationFailed(f"Bảng {block_id} đã đổi (phiên bản hiện tại {current}, thao tác gửi theo phiên bản {base_version}): "
                                   "gọi canvas_read lấy lại id dòng, cột và số liệu rồi gửi lại.")
        pending = target.get("proposal") or {}
        if pending.get("action") == "delete":
            raise ValidationFailed(f"Bảng {block_id} đang có đề xuất xóa chờ người dùng quyết định.")
        base = pending.get("table") or target["table"]
        spec, notes = tables.apply(base, ops)
        if spec == base or spec == target.get("table"):
            raise ValidationFailed("Các thao tác không làm đổi bảng; không có gì để đề xuất.")
        reasons = [pending.get("note", ""), note.strip()] if pending.get("table") else [note.strip()]
        target["proposal"] = {"action": "insert" if pending.get("action") == "insert" else "replace", "text": tables.summary(spec),
                              "note": "; ".join(dict.fromkeys(r for r in reasons if r)), "table": spec}
        return target, notes

    def _mark_stale(self, table_id: str, old: dict[str, Any], new: dict[str, Any]) -> None:
        """Marks the passages that quote figures a change took out of a table (see `tables.dropped_figures`)."""
        gone = set(tables.dropped_figures(old, new))
        if not gone:
            return
        for block in self.blocks:
            if block["kind"] == "table" or block["id"] == table_id:
                continue
            hit = tables.figures_in(block["text"]) & gone
            if not hit:
                continue
            stale = block.get("stale") or {"tables": [], "figures": []}
            figures = sorted({*(tables.parse_number(f) for f in stale["figures"]), *hit})
            block["stale"] = {"tables": list(dict.fromkeys([*stale["tables"], table_id])),
                              "figures": [tables.format_number(f) for f in figures]}

    # ----- the user's direct edits -----
    def user_edit(self, *, blocks: list[dict[str, Any]] | None = None, insert: dict[str, Any] | None = None,
                  delete: list[str] | None = None, reviewed: list[str] | None = None) -> list[str]:
        """Applies the user's own edits to the body; an edited block becomes theirs and loses any pending proposal.

        Args:
            blocks: ``[{"id", "text"}]``, or ``[{"id", "table"}]`` for a table block.
            insert: One block to add: ``{"after", "kind", "text", "table"?}`` ("after" empty = at the start).
            delete: Ids of blocks to remove.
            reviewed: Ids of passages whose "figures changed" mark the user dismisses.

        Returns:
            The ids of the blocks touched.

        Raises:
            ValidationFailed: An unknown block, an empty or overlong text, a table block edited without a spec.
        """
        touched: list[str] = []
        for change in blocks or []:
            target = self.block(change["id"])
            if target["kind"] == "table":
                if change.get("table") is None:
                    raise ValidationFailed("Đoạn này là bảng: gửi bảng đã sửa trong 'table'.")
                old = target["table"]
                _, target["text"], target["table"] = self._shape("table", "", change["table"])
                self._mark_stale(target["id"], old, target["table"])
            else:
                text = (change.get("text") or "").strip()
                if blank(clean(text)) or len(text) > MAX_TEXT:
                    raise ValidationFailed("Đoạn trống hoặc quá dài (muốn bỏ đoạn thì xóa nó).")
                target["kind"], target["text"], _ = self._shape(target["kind"], text)
                target.pop("stale", None)
            target["owner"], target["proposal"] = "user", None
            target["version"] = target.get("version", 1) + 1
            touched.append(target["id"])
        for block_id in reviewed or []:
            if self.block(block_id).pop("stale", None) is not None:
                touched.append(block_id)
        for block_id in delete or []:
            self.blocks.remove(self.block(block_id))
            touched.append(block_id)
        if insert:
            after = insert.get("after")
            new = self._make(insert.get("kind", "para"), insert.get("text", ""), "user", insert.get("table"))
            index = 0 if not after else self.blocks.index(self.block(after)) + 1
            self.blocks.insert(index, new)
            touched.append(new["id"])
        return touched
