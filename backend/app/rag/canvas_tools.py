"""Tools the assistant uses to draft a document in the conversation's canvas.

They run in the tool process of one conversation (see `app.rag.mcp_server`) and edit the draft through `app.services.drafts`, the
same code path as the user's own edits, so the ownership rules hold: the assistant fills what is blank, never overwrites what the
person wrote, and proposes (not applies) changes to text the person owns or has accepted.

The docstrings of the `canvas_*` methods are the tool descriptions the model reads.
"""
from __future__ import annotations

from typing import Any, Literal

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.errors import AppError
from app.drafting import structure, style, style_check, templates
from app.models import ChatSession, User
from app.org import Scope
from app.search import QdrantIndex
from app.services import drafts, organization


class SubColumnIn(BaseModel):
    """A sub-column under a group heading.

    Attributes:
        id: Column id ("c3"); optional, given so that formulas and sums in the same table can name it.
        label: Heading text.
        align: Cell alignment; chosen from the content when omitted.
        formula: Worked out on every ordinary row from other columns of the row: column ids, numbers, + - * /, parentheses and
            sum(cN) (the column's total), e.g. "c4 * c5" or "c5 / sum(c5) * 100".
    """

    id: str = ""
    label: str
    align: Literal["left", "center", "right"] | None = None
    formula: str = ""


class ColumnIn(SubColumnIn):
    """A column of a table.

    Attributes:
        children: Sub-columns, making this column a group heading over them (two heading levels at most; then the formulas go
            on the sub-columns).
    """

    children: list[SubColumnIn] = []


class RowIn(BaseModel):
    """A row of a table.

    Attributes:
        id: Row id ("r5"); optional.
        type: ``row`` (one cell per leaf column), ``group`` (a heading line such as "I" | "Trang thiết bị phần cứng", bold),
            ``section`` (one text across the table, "Bổ sung (…)"), ``total`` (the "Cộng" line, bold).
        cells: Cell texts, left to right; missing trailing cells are empty. Figures are written the Vietnamese way ("1.200",
            "12,5"); a figure nobody gave is "…".
        sum: For a ``total`` or ``group`` row, the column ids it adds up (its cells there are worked out).
        scope: For a ``total`` row: ``all`` the ordinary rows of the table, or ``group`` those of the group it stands in. A
            ``group`` row always adds the rows under it.
    """

    id: str = ""
    type: Literal["row", "group", "section", "total"] = "row"
    cells: list[str] = []
    sum: list[str] = []
    scope: Literal["all", "group"] | None = None


class TableIn(BaseModel):
    """A table.

    Attributes:
        columns: The columns, left to right.
        rows: The rows, top to bottom. Figures nobody gave are "…".
        landscape: Force the page orientation of the table's appendix; by default it turns landscape when the table is too wide.
    """

    columns: list[ColumnIn]
    rows: list[RowIn] = []
    landscape: bool | None = None


class TableOpIn(BaseModel):
    """One edit of a table, naming rows and columns by id (see `CanvasTools.canvas_edit_table`)."""

    op: Literal["set", "set_row", "insert_row", "delete_row", "insert_column", "delete_column", "rename_column", "formula", "total"]
    row: str = ""
    column: str = ""
    value: str = ""
    cells: list[str] | None = None
    type: Literal["row", "group", "section", "total"] | None = None
    after: str = ""
    before: str = ""
    parent: str = ""
    label: str = ""
    align: Literal["left", "center", "right"] | None = None
    formula: str = ""
    values: dict[str, str] | None = None
    columns: list[str] | None = None
    scope: Literal["all", "group"] | None = None


class BlockIn(BaseModel):
    """One block of the body.

    Attributes:
        kind: ``heading``, ``para``, ``item``, ``table`` or ``appendix`` (see `CanvasTools.canvas_set_content`).
        text: The text; for an appendix its title; ignored for a table.
        table: The table, for kind ``table``.
    """

    kind: Literal["heading", "para", "item", "table", "appendix"] = "para"
    text: str = ""
    table: TableIn | None = None


def _fail(exc: AppError) -> ToolError:
    """The tool error the model reads: the message only (any other exception reaches it as a bare "Error executing tool")."""
    return ToolError(exc.message)


def _summary(content: drafts.DraftContent) -> dict[str, Any]:
    """A compact view of a draft for the model.

    Args:
        content: The draft.

    Returns:
        ``{"fields", "blocks", "missing"}``. Each block has its ``version``; a table block includes its spec (with the ids of its
        rows and columns), orientation, cells still "…" and what it could not compute; an appendix block its label; a passage
        quoting figures a table no longer holds its ``stale`` mark.
    """
    shown = content.view()
    keys = ("table", "label", "landscape", "too_wide", "blanks", "problems", "stale")
    return {"fields": {k: {"label": v["label"], "text": v["text"], "owner": v["owner"], "needs_input": v["needs_input"]}
                       for k, v in shown["fields"].items()},
            "blocks": [{"id": b["id"], "kind": b["kind"], "text": b["text"], "owner": b["owner"], "version": b["version"],
                        **{k: b[k] for k in keys if b.get(k) not in (None, [], "")},
                        **({"proposal": b["proposal"]} if b.get("proposal") else {})} for b in shown["blocks"]],
            "missing": shown["missing"]}


class CanvasTools:
    """Draft tools for one conversation and user.

    Attributes:
        session_id: The conversation.
        user_id: The user the assistant works for.
        store: The document index and the user's scope in it, where `canvas_style` finds example documents; without it the style
            guide has no examples.
    """

    def __init__(self, session_id: str, user_id: int, store: tuple[QdrantIndex, Scope] | None = None):
        self.session_id, self.user_id, self.store = session_id, user_id, store

    def _open(self) -> tuple[Session, User, ChatSession]:
        """Opens a database session with the user and the conversation.

        Returns:
            ``(db, user, session)``; the caller closes `db`.

        Raises:
            ToolError: The user or the conversation is gone, or the conversation is not the user's.
        """
        db = SessionLocal()
        user, session = db.get(User, self.user_id), db.get(ChatSession, self.session_id)
        if user is None or session is None or session.user_id != user.id:
            db.close()
            raise ToolError("Không xác định được cuộc trò chuyện.")
        return db, user, session

    def canvas_create(self, kind: str, replace: bool = False, unit: str = "") -> dict[str, Any]:
        """Find structure from standard templates.

        Opens the canvas with a template of Thông tư 68/2023/TT-BQP. The system fills the national name, motto, issuing body,
        number symbol, "Lưu" line and the usual signing authority from the drafting unit, and today's date. Each conversation has
        one draft.

        Args:
            kind: CV (Công văn), KH (Kế hoạch), BC (Báo cáo), TB (Thông báo), TTr (Tờ trình), HD (Hướng dẫn), CTr (Chương trình),
                PA (Phương án), ĐA (Đề án), DA (Dự án), CT (Chỉ thị), QĐ (Quyết định), NQ (Nghị quyết), QC (Quy chế),
                QyĐ (Quy định), CĐ (Công điện), GM (Giấy mời).
            replace: Replace the conversation's current draft with a new one.
            unit: The drafting unit (id or name, e.g. "Ban CNTT") when the user says whom the document is written for; empty for
                the user's own unit. Only the user's unit or a unit under it is allowed.

        Returns:
            The template's fields and layout guide, the fields still missing, the drafting unit, and its writing style.
        """
        db, user, session = self._open()
        try:
            row = drafts.create(db, user, session, kind, replace=replace, unit=unit)
            db.commit()
            content = drafts.content_of(row)
            picked = style.choice(row.style)
            return {"template": content.template.name, "model": content.template.model, "guide": content.template.guide,
                    "fields": {k: {"label": templates.label_of(k), "owner": v["owner"], "text": v["text"]} for k, v in content.fields.items()},
                    "missing": content.missing(),
                    "unit": drafts.unit_name(row.unit_id),
                    "style": style.guide(organization.tree(), row.unit_id, content.template, choice=picked),
                    "chosen": picked,
                    "note": "Nội dung chính chưa có: viết theo 'style' (văn phong của đơn vị người dùng và phong cách trong 'style.chosen') "
                            "bằng canvas_set_content; phong cách đã chọn không được bỏ thành phần bắt buộc. Cần văn bản mẫu cùng loại, "
                            "gần chủ đề thì gọi canvas_style(topic=...). Điền trích yếu, kính gửi, căn cứ, nơi nhận bằng canvas_set_fields."}
        except AppError as exc:
            db.rollback()
            raise _fail(exc) from exc
        finally:
            db.close()

    def canvas_style(self, topic: str = "", kind: str = "", section: str = "") -> dict[str, Any]:
        """Find style from standard templates.
        Args:
            topic: Subject to find example documents for; the draft's title by default.
            kind: Kind symbol (CV, KH, BC, ...); the kind of the open draft by default.
            section: Name of the section being written (e.g. "Tổ chức thực hiện"); each example then carries a 'passage', the
                opening of that section, to learn the wording from.

        Returns:
            The style guide; 'chosen' is the preset and level of detail the user picked, 'examples' the example documents.

        Raises:
            ToolError: No draft is open and no kind is given, or the kind is unknown.
        """
        db, user, _ = self._open()
        try:
            row = drafts.find(db, self.session_id)
            code = kind or (row.template if row is not None else "")
            if not code:
                raise ToolError("Chưa có bản dự thảo: cho biết loại văn bản (kind), ví dụ 'KH'.")
            try:
                template = templates.get(code)
            except KeyError:
                raise ToolError(f"Chưa có mẫu '{code}'.") from None
            picked = style.choice(row.style if row is not None else None)
            unit = drafts.unit_of(db, row) if row is not None else user.unit_id
            out = style.guide(organization.tree(), unit, template, choice=picked)
            topic = topic or (row.title if row is not None else "")
            if self.store is not None:
                try:
                    out["examples"] = style.examples(*self.store, template, topic, section=section)
                except Exception as exc:  # noqa: BLE001  (the index or the embedding server is down: the guide still helps)
                    out["examples_error"] = f"Không lấy được văn bản mẫu ({type(exc).__name__})."
            return out
        finally:
            db.close()

    def canvas_read(self) -> dict[str, Any]:
        """Reads the current draft. Call it before editing.

        Returns:
            The fields, the blocks with their ids and owners (tables with their spec, appendices with their label), the pending
            proposals, and the fields still missing.
        """
        db, _, _ = self._open()
        try:
            return _summary(drafts.content_of(drafts.get(db, self.session_id)))
        except AppError as exc:
            raise _fail(exc) from exc
        finally:
            db.close()

    def canvas_set_fields(self, fields: dict[str, str]) -> dict[str, Any]:
        """Fills fields of the document.

        A field the system filled or the user typed is refused (see 'refused'); only a blank field or one still holding "…" can
        be filled. Write plain text, without Markdown.

        Args:
            fields: ``{key: text}``. Keys: trich_yeu (subject; for a công văn the part after "V/v"), kinh_gui (one addressee per
                line), can_cu (one legal basis per line, starting with "Căn cứ"), noi_nhan (one recipient per line starting with
                "- "; "- Như trên;" is added when there is a "Kính gửi"; on the last line "- Lưu: VT, <drafting office>. …." leave
                the drafter's initials as "…"), quyen_han (signing authority, one line each, e.g. "KT. THAM MƯU TRƯỞNG" /
                "PHÓ THAM MƯU TRƯỞNG"), nguoi_ky, dia_danh_ngay, ten_loai, co_quan_ban_hanh, co_quan_chu_quan, so_ky_hieu.

        Returns:
            ``{"applied", "refused", "missing"}``.
        """
        db, _, _ = self._open()
        try:
            row = drafts.get(db, self.session_id)
            applied, refused = drafts.set_fields(db, row, fields)
            db.commit()
            return {"applied": applied, "refused": refused, "missing": drafts.content_of(row).missing()}
        except AppError as exc:
            db.rollback()
            raise _fail(exc) from exc
        finally:
            db.close()

    def canvas_set_content(self, blocks: list[BlockIn]) -> dict[str, Any]:
        """Writes the whole body of the document.

        Use it only while no block was written by the user; to change single blocks use canvas_edit_block. Write plain text
        without Markdown (**, #): bold follows the kind, as Thông tư 68 prescribes. "./." is added at the end of the last paragraph
        of the main body.

        Args:
            blocks: The blocks in order. kind 'heading' = a roman section heading ("I. MỤC ĐÍCH") or a short khoản title
                ("1. Thời gian, địa điểm"), the whole line bold; 'para' = a paragraph (one starting with "1." that is a sentence
                gets only its number bold); 'item' = a "- ", "+ " or "a)" line, regular ("- " is added when the mark is missing);
                'table' = a table, given in `table` (never a Markdown table; figures nobody gave are "…"; totals and derived
                figures through 'sum' rows and column 'formula', never computed by you); 'appendix' = the start of an
                appendix, text = its title, and the blocks after it belong to it (the system prints "Phụ lục", "(Kèm theo … số
                … ngày … của …)", numbers its pages separately and turns it landscape when a table is wide). The body must cite
                each appendix ("chi tiết tại Phụ lục kèm theo").

        Returns:
            ``{"block_ids", "checks"}``: the new ids, words to avoid, and structure problems (numbering, repeated passages, an
            appendix cited but missing).
        """
        db, _, _ = self._open()
        try:
            row = drafts.get(db, self.session_id)
            ids = drafts.set_content(db, row, [b.model_dump() for b in blocks])
            db.commit()
            body = "\n".join(block.text for block in blocks if block.kind != "table")
            return {"block_ids": ids, "checks": style_check.wording(body) + structure.check(drafts.content_of(row))}
        except AppError as exc:
            db.rollback()
            raise _fail(exc) from exc
        finally:
            db.close()

    def canvas_edit_block(self, action: Literal["replace", "delete", "insert"], block_id: str = "", text: str = "", note: str = "",
                          kind: Literal["heading", "para", "item", "table", "appendix"] = "para",
                          table: TableIn | None = None) -> dict[str, Any]:
        """Proposes a change to the body; the user accepts or rejects it.

        Propose only changes of content: bold and numbering are laid out by the system from the kind, and a proposal that changes
        nothing else is refused. If 'checks' lists "Có thêm …" for information the user did not give, propose again without it.

        Args:
            action: 'replace' the text of block_id (for a table block, send the whole new table in `table`; to change some cells,
                rows or columns use canvas_edit_table instead); 'delete' block_id; 'insert' a new block (kind and text, or
                kind='table' with `table`) after block_id.
            block_id: The block to change; for 'insert' the block to insert after ("" = at the start).
            text: The new text.
            note: A short reason shown to the user.
            kind: Kind of the inserted block.
            table: The table for kind 'table'.

        Returns:
            ``{"block_id", "status", "checks"}``. For a replacement 'checks' lists figures, names and dates in the proposal that the
            passage did not have, words to avoid, and a warning when the proposal replaces almost every word of the passage (maybe
            the wrong block_id: read again with canvas_read) or repeats another passage.
        """
        db, _, _ = self._open()
        try:
            block = drafts.propose(db, drafts.get(db, self.session_id), block_id, action, text, note, kind,
                                   table.model_dump() if table else None)
            db.commit()
            checks = (block.get("proposal") or {}).get("checks", [])
            return {"block_id": block["id"], "status": "đang chờ người dùng chấp nhận", "checks": checks}
        except AppError as exc:
            db.rollback()
            raise _fail(exc) from exc
        finally:
            db.close()

    def canvas_edit_table(self, block_id: str, base_version: int, ops: list[TableOpIn], note: str = "") -> dict[str, Any]:
        """Proposes changes to some cells, rows or columns of a table; the user accepts or rejects them.

        Name rows and columns by the ids canvas_read shows ("r3", "c4"); they stay the same when others are inserted or deleted.
        Several calls on the same table add up to one proposal. Never compute totals or derived figures yourself: use 'total'
        and 'formula'. A figure the user has not given is "…"; never invent one.

        Args:
            block_id: The table block.
            base_version: The block's 'version' from canvas_read. If the table changed since, the call fails: read again.
            ops: The edits, applied in order:
                {"op": "set", "row", "column", "value"} sets one cell (a section row's text: column not needed);
                {"op": "set_row", "row", "cells"?, "type"?} rewrites a row's cells (left to right) or its type;
                {"op": "insert_row", "after"? | "before"?, "type"?, "cells"?, "columns"?, "scope"?} adds a row (at the end
                without after/before; type 'total' with 'columns' makes a "Cộng" row adding those columns);
                {"op": "delete_row", "row"};
                {"op": "insert_column", "label", "after"? | "before"?, "parent"?, "align"?, "formula"?, "values"?} adds a column
                (after/before a column id; 'parent' = the group column to put it under; 'values' = {row id: text});
                {"op": "delete_column", "column"} (a group column with its sub-columns);
                {"op": "rename_column", "column", "label"};
                {"op": "formula", "column", "formula"} works the column out on every ordinary row: column ids, numbers,
                + - * /, parentheses, sum(cN) = total of a column, e.g. "c4 * c5", "c5 / sum(c5) * 100"; "" removes it;
                {"op": "total", "row", "columns", "scope"?} makes a total or group row add up columns ('all' rows of the table
                or its 'group'); [] stops it.
                Computed cells cannot be set by hand. A cell needing a "…" figure, text or a division by zero shows "…".
            note: A short reason shown to the user.

        Returns:
            ``{"block_id", "status", "notes", "table", "checks"}``: the ids of rows and columns created or removed, the proposed
            table, and what it could not compute or still lacks.
        """
        db, _, _ = self._open()
        try:
            row = drafts.get(db, self.session_id)
            block, notes = drafts.edit_table(db, row, block_id, base_version, [op.model_dump(exclude_none=True) for op in ops], note)
            db.commit()
            proposal = block["proposal"]
            return {"block_id": block["id"], "status": "đang chờ người dùng chấp nhận", "notes": notes, "table": proposal["table"],
                    "checks": proposal.get("checks", [])}
        except AppError as exc:
            db.rollback()
            raise _fail(exc) from exc
        finally:
            db.close()

    def canvas_check(self) -> dict[str, Any]:
        """Checks the draft before it is handed over.

        The draft is rendered as a .docx and checked against Thông tư 68/2023/TT-BQP, then its structure (Markdown left over,
        repeated passages, numbering of sections and khoản, "Như trên", appendices cited and present) and its wording (words to
        avoid, the unit's usual sections, gaps still holding "…"). The number, symbol and signature are completed later by the
        registry clerk and the signer, so they are not counted.

        Returns:
            ``{"counts", "findings", "checked_at", "style"}``: the errors and warnings to fix.
        """
        db, _, _ = self._open()
        try:
            return drafts.check(db, drafts.get(db, self.session_id))
        except AppError as exc:
            raise _fail(exc) from exc
        finally:
            db.close()
