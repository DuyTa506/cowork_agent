"""The draft ("canvas") of a conversation: create, change (by the assistant or the user), check, export, save to the store.

The assistant's tools (in the tool process) and the HTTP API (in the web process) both go through this module, so the rules in
`app.drafting.content` apply no matter who edits. Functions flush but do not commit; the caller owns the transaction.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from sqlalchemy import delete as sql_delete, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.drafting import structure, style, style_check, tables, templates
from app.drafting.check import check_draft
from app.drafting.content import HISTORY_KEEP, DraftContent, Issuer, blank, with_luu
from app.drafting.render import render, slug
from app.models import ChatSession, Draft, DraftRevision, User
from app.models.base import now_utc

from . import documents, organization


# ----- loading -----
def find(db: Session, session_id: str) -> Draft | None:
    """The draft of a conversation, if it has one."""
    return db.scalar(select(Draft).where(Draft.session_id == session_id))


def get(db: Session, session_id: str) -> Draft:
    """The draft of a conversation; `NotFound` when there is none."""
    row = find(db, session_id)
    if row is None:
        raise NotFound("Cuộc trò chuyện chưa có bản dự thảo.")
    return row


def content_of(row: Draft) -> DraftContent:
    """The editable content of a stored draft."""
    return DraftContent.load(templates.get(row.template), row.fields, row.blocks, row.counter)


def _store(row: Draft, content: DraftContent, by: str, summary: str) -> None:
    """Writes `content` back, bumps the version and logs the change."""
    row.fields, row.blocks, row.counter = content.fields, content.blocks, content.counter
    row.version += 1
    row.updated_at = now_utc()
    spec = content.fields.get("trich_yeu")
    if spec and spec["text"].strip():
        row.title = spec["text"].strip()[:300]
    row.history = [*row.history, {"version": row.version, "at": row.updated_at.isoformat(), "by": by, "summary": summary}][-HISTORY_KEEP:]
    row.fields = dict(row.fields)  # a new object, so the JSON column registers the change
    row.blocks = [dict(b) for b in row.blocks]


# ----- presentation -----
def template_info(template: templates.Template) -> dict[str, Any]:
    """The template as the API presents it."""
    return {"code": template.code, "kind": template.kind, "name": template.name, "doc_type": template.kind,
            "authority": template.authority}


def view(row: Draft) -> dict[str, Any]:
    """The draft as the API presents it."""
    content = content_of(row)
    return {"id": row.id, "title": row.title or content.template.name, "version": row.version, "updated_at": row.updated_at,
            "template": template_info(content.template), **content.view(), "style": style.choice(row.style),
            "style_options": style.options(), "history": row.history, "unit_id": row.unit_id,
            "unit_name": unit_name(row.unit_id) if row.unit_id else ""}


def snapshot(db: Session, session_id: str) -> dict[str, Any] | None:
    """`view` of the conversation's draft, or None."""
    row = find(db, session_id)
    return view(row) if row else None


def catalogue() -> list[dict[str, Any]]:
    """The kinds of document that can be drafted."""
    return [{**template_info(t), "fields": list(t.fields), "required": sorted(t.required)} for t in templates.all_templates().values()]


# ----- the drafting unit -----
def issuer_of(unit_id: str, template: templates.Template) -> Issuer:
    """The header a draft starts with, as its unit issues that kind (see `app.drafting.style.issuer_for`).

    A phòng of Bộ Tham mưu writes under "BỘ THAM MƯU", with its own office in the symbol and on the "Lưu" line.

    Args:
        unit_id: The drafting unit.
        template: The kind of document.

    Returns:
        The issuer.
    """
    return style.issuer_for(organization.tree(), unit_id, template)


def unit_of(db: Session, row: Draft) -> str:
    """The unit a draft is written for: the one chosen on the canvas, else its author's."""
    return row.unit_id or _unit_of(db, row)


def unit_name(unit_id: str) -> str:
    """The name of a unit, or its id when the unit tree does not know it."""
    tree = organization.tree()
    return tree.get(unit_id).name if unit_id in tree.units else unit_id


def resolve_unit(user: User, raw: str) -> str:
    """Finds the unit a user asks to draft for.

    A user drafts for their own unit or one under it (a staff officer of Bộ Tham mưu for Ban CNTT, not the reverse).

    Args:
        user: The author.
        raw: A unit id or a name ("Ban CNTT"); empty for the user's own unit.

    Returns:
        The unit id.

    Raises:
        ValidationFailed: An unknown or ambiguous name, or a unit outside the user's own.
    """
    tree = organization.tree()
    raw = (raw or "").strip()
    if not raw or raw == user.unit_id:
        return user.unit_id
    allowed = tree.subtree(user.unit_id) if user.unit_id in tree.units else frozenset({user.unit_id})
    if raw in tree.units:
        found = [raw]
    else:
        match = tree.resolve_header(raw)
        found = [match.unit_id] if match.unit_id else list(match.candidates)
        found = [u for u in found if u in allowed] or found
    if not found:
        raise ValidationFailed(f"Không tìm thấy đơn vị '{raw}'.")
    if len(found) > 1:
        names = "; ".join(f"{unit_name(u)} ({u})" for u in found[:6])
        raise ValidationFailed(f"'{raw}' trùng tên nhiều đơn vị: {names}. Hãy chọn mã đơn vị.")
    if found[0] not in allowed:
        raise ValidationFailed("Chỉ soạn được văn bản cho đơn vị mình hoặc đơn vị cấp dưới.")
    return found[0]


def set_unit(db: Session, row: Draft, user: User, raw: str) -> str:
    """Writes a draft for another unit.

    The header, the symbol, the "Lưu" office and the suggested signer follow the new unit; what the user typed is kept.

    Args:
        db: Database session (flushed, not committed).
        row: The draft.
        user: The user asking (see `resolve_unit` for which units they may choose).
        raw: A unit id or name.

    Returns:
        The unit id.

    Raises:
        ValidationFailed: See `resolve_unit`.
    """
    unit = resolve_unit(user, raw)
    if unit == unit_of(db, row):
        return unit
    content = content_of(row)
    issuer = issuer_of(unit, content.template)
    fresh = DraftContent.new(content.template, issuer)
    for key, spec in content.fields.items():
        new = fresh.fields[key]
        if key in ("co_quan_chu_quan", "co_quan_ban_hanh", "so_ky_hieu") and (spec["owner"] == "system" or blank(spec["text"])):
            content.fields[key] = new
        elif key == "quyen_han" and (spec["owner"] == "assistant" or blank(spec["text"])):
            content.fields[key] = new
        elif key == "noi_nhan" and spec["owner"] != "user":
            spec["text"] = with_luu(spec["text"], issuer.luu_line())
    row.unit_id = unit
    _store(row, content, "user", f"Soạn cho {unit_name(unit)}")
    db.flush()
    return unit


# ----- creation -----
def create(db: Session, user: User, session: ChatSession, kind: str, *, title: str = "", replace: bool = False, by: str = "assistant",
           unit: str = "") -> Draft:
    """Opens a draft in a conversation.

    Args:
        db: Database session (flushed, not committed).
        user: The author.
        session: The conversation.
        kind: A template code or kind symbol such as ``CV``.
        title: Initial title (the trích yếu replaces it once written).
        replace: Replace the conversation's existing draft.
        by: ``assistant`` or ``user``, for the history.
        unit: The drafting unit, as an id or a name; the user's own unit when empty.

    Returns:
        The new draft.

    Raises:
        ValidationFailed: Unknown kind, or a unit the user may not draft for (see `resolve_unit`).
        Conflict: The conversation has a draft already and `replace` is not set.
    """
    unit_id = resolve_unit(user, unit)
    try:
        template = templates.get(kind)
    except KeyError:
        names = ", ".join(f"{t.kind} ({t.name})" for t in templates.all_templates().values())
        raise ValidationFailed(f"Chưa có mẫu '{kind}'. Các loại soạn được: {names}.") from None
    existing = find(db, session.id)
    if existing is not None:
        if not replace:
            raise Conflict("Cuộc trò chuyện đã có bản dự thảo; sửa bản đó hoặc đặt replace=true để thay bằng bản mới.")
        db.delete(existing)
        db.flush()
    content = DraftContent.new(template, issuer_of(unit_id, template))
    row = Draft(session_id=session.id, user_id=user.id, template=template.code, doc_type=template.kind, title=title.strip()[:300],
                unit_id=unit_id, fields=content.fields, blocks=content.blocks, counter=0, version=0, history=[])
    db.add(row)
    _store(row, content, by, f"Mở mẫu {template.name}")
    db.flush()
    return row


def set_style(db: Session, row: Draft, raw: dict[str, Any]) -> dict[str, str]:
    """Stores the preset and detail level the user picked. Unknown values fall back to the defaults; an unchanged choice is a no-op."""
    picked = style.choice(raw)
    if style.choice(row.style) == picked:
        return picked
    row.style = dict(picked)
    row.version += 1
    row.updated_at = now_utc()
    chosen = style._chosen(picked)
    row.history = [*row.history, {"version": row.version, "at": row.updated_at.isoformat(), "by": "user",
                                  "summary": f"Chọn văn phong {chosen['preset_name']}, mức chi tiết {chosen['detail_name']}"}][-HISTORY_KEEP:]
    db.flush()
    return picked


def delete(db: Session, session_id: str) -> None:
    """Drops the draft of a conversation and the record of its proposals (no-op when there is none)."""
    db.execute(sql_delete(DraftRevision).where(DraftRevision.session_id == session_id))
    row = find(db, session_id)
    if row is not None:
        db.delete(row)


# ----- changes by the assistant -----
def set_fields(db: Session, row: Draft, values: dict[str, str], by: str = "assistant") -> tuple[list[str], dict[str, str]]:
    """Sets header/signature fields; returns ``(applied, refused)`` (see `DraftContent.set_fields`)."""
    content = content_of(row)
    applied, refused = content.set_fields(values, by)
    if applied:
        _store(row, content, by, "Điền " + ", ".join(templates.label_of(k) for k in applied))
        db.flush()
    return applied, refused


def set_content(db: Session, row: Draft, items: list[dict[str, Any]], by: str = "assistant") -> list[str]:
    """Replaces the body of a draft.

    Args:
        db: Database session (flushed, not committed).
        row: The draft.
        items: ``[{"kind", "text", "table"?}]`` (see `DraftContent.set_content`).
        by: ``assistant`` or ``user``.

    Returns:
        The new block ids.
    """
    content = content_of(row)
    ids = content.set_content(items, by)
    _store(row, content, by, f"{'Trợ lý' if by == 'assistant' else 'Người dùng'} soạn nội dung ({len(ids)} đoạn)")
    db.flush()
    return ids


def propose(db: Session, row: Draft, block_id: str, action: str, text: str = "", note: str = "", kind: str = "para",
            table: dict[str, Any] | None = None) -> dict[str, Any]:
    """Records the assistant's proposed change to the body (see `DraftContent.propose`).

    A text proposal carries checks for the user: for a replacement the style check (new facts, avoided words), and for both a
    replacement and an insertion the structure check (a proposal that looks aimed at another passage, or repeats one).

    Args:
        db: Database session (flushed, not committed).
        row: The draft.
        block_id: Block to replace or delete, or after which to insert.
        action: ``replace``, ``delete`` or ``insert``.
        text: The proposed text.
        note: A short reason shown to the user.
        kind: Kind of an inserted block.
        table: The spec of a proposed table.

    Returns:
        The block carrying the proposal.
    """
    content = content_of(row)
    before = content.block(block_id)["text"] if action == "replace" else ""
    block = content.propose(block_id, action, text, note, kind, table)
    proposal = block.get("proposal")
    if proposal and proposal.get("table"):
        proposal["checks"] = _table_checks(proposal["table"])
    elif action == "replace" and proposal:
        proposal["checks"] = (style_check.compare(before, proposal["text"]) + style_check.wording(proposal["text"])
                              + structure.proposal_checks(content, block["id"], before, proposal["text"]))
    elif action == "insert" and proposal:
        proposal["checks"] = structure.proposal_checks(content, block["id"], "", proposal["text"])
    _store(row, content, "assistant", f"Đề xuất {_ACTION[action]} ({block['id']})")
    db.flush()
    return block


def edit_table(db: Session, row: Draft, block_id: str, base_version: int, ops: list[dict[str, Any]],
               note: str = "") -> tuple[dict[str, Any], list[str]]:
    """Records the assistant's edits to a table as a proposal (see `DraftContent.edit_table`).

    Args:
        db: Database session (flushed, not committed).
        row: The draft.
        block_id: The table block.
        base_version: The block's version the assistant read.
        ops: Edits by row and column id (see `app.drafting.tables.apply`).
        note: A short reason shown to the user.

    Returns:
        ``(the block carrying the proposal, notes naming the rows and columns created or removed)``; the proposal's checks list
        what the table could not work out and the cells still holding "…".
    """
    content = content_of(row)
    block, notes = content.edit_table(block_id, base_version, ops, note)
    block["proposal"]["checks"] = _table_checks(block["proposal"]["table"])
    _store(row, content, "assistant", f"Đề xuất sửa bảng ({block_id})")
    db.flush()
    return block, notes


def _table_checks(spec: dict[str, Any]) -> list[dict[str, str]]:
    """Checks shown with a proposed table: what its formulas and sums could not work out, and the figures still missing."""
    out = [{"severity": "warning", "kind": "table", "message": problem, "where": ""} for problem in tables.problems(spec)]
    missing = tables.blanks(spec)
    if missing:
        out.append({"severity": "info", "kind": "blanks", "message": f"Còn {missing} ô '…' chờ người dùng điền số liệu.", "where": ""})
    return out


_ACTION = {"replace": "sửa đoạn", "delete": "xóa đoạn", "insert": "thêm đoạn"}


# ----- changes by the user -----
def _unit_of(db: Session, row: Draft) -> str:
    user = db.get(User, row.user_id)
    return user.unit_id if user is not None else ""


def _record(db: Session, row: Draft, *, block_id: str, outcome: str, before: str, proposed: str, final: str, checks: list) -> None:
    db.add(DraftRevision(session_id=row.session_id, user_id=row.user_id, unit_id=_unit_of(db, row), template=row.template,
                         block_id=block_id, outcome=outcome, before=before, proposed=proposed, final=final, checks=list(checks or [])))


def decide(db: Session, row: Draft, block_id: str, accept: bool) -> None:
    """Accepts or rejects the assistant's proposal on a block, and records the pair for the dashboard."""
    content = content_of(row)
    target = content.block(block_id)
    proposal = dict(target.get("proposal") or {})
    action = proposal.get("action", "")
    before = "" if action == "insert" else target["text"]
    proposed = proposal.get("text", "")
    applied = content.accept(block_id) if accept else content.reject(block_id)
    if accept and applied != "delete":
        final = proposed
    elif not accept and applied != "insert":
        final = before
    else:
        final = ""
    _store(row, content, "user", f"{'Chấp nhận' if accept else 'Từ chối'} đề xuất {_ACTION[applied]} ({block_id})")
    _record(db, row, block_id=block_id, outcome="accepted" if accept else "rejected", before=before, proposed=proposed,
            final=final, checks=proposal.get("checks") or [])
    db.flush()


def _from_assistant(db: Session, session_id: str, block_id: str, old: dict[str, str]) -> bool:
    """True when the passage was written by the assistant, or is still the text of a proposal the user accepted."""
    if old["owner"] == "assistant":
        return True
    last = db.scalar(select(DraftRevision).where(DraftRevision.session_id == session_id, DraftRevision.block_id == block_id,
                                                  DraftRevision.outcome == "accepted").order_by(DraftRevision.id.desc()))
    return last is not None and last.final == old["text"]


def user_edit(db: Session, row: Draft, *, fields: dict[str, str] | None = None, blocks: list[dict[str, Any]] | None = None,
              insert: dict[str, Any] | None = None, delete_ids: list[str] | None = None, reviewed: list[str] | None = None) -> None:
    """The user's direct edits to fields and body. Rewriting a passage the assistant wrote is recorded.

    Args:
        db: Database session (flushed, not committed).
        row: The draft.
        fields: ``{key: text}``.
        blocks: ``[{"id", "text"}]`` or ``[{"id", "table"}]``.
        insert: One block to add (see `DraftContent.user_edit`).
        delete_ids: Blocks to remove.
        reviewed: Passages whose "figures changed" mark the user dismisses.

    Raises:
        ValidationFailed: A field the template does not have, or an invalid block (see `DraftContent.user_edit`).
    """
    content = content_of(row)
    prior = {block["id"]: {"text": block["text"], "owner": block["owner"]} for block in content.blocks}
    notes: list[str] = []
    if fields:
        applied, refused = content.set_fields(fields, "user")
        if refused:
            raise ValidationFailed("; ".join(refused.values()))
        notes.append("sửa " + ", ".join(templates.label_of(k) for k in applied))
    touched = content.user_edit(blocks=blocks, insert=insert, delete=delete_ids, reviewed=reviewed)
    if touched:
        notes.append(f"sửa nội dung ({', '.join(touched)})")
    if notes:
        _store(row, content, "user", "Người dùng " + "; ".join(notes))
        for change in blocks or []:
            old = prior.get(change["id"])
            current = next((block for block in content.blocks if block["id"] == change["id"]), None)
            if old is None or current is None or current["text"] == old["text"]:
                continue
            if _from_assistant(db, row.session_id, change["id"], old):
                _record(db, row, block_id=change["id"], outcome="edited_after", before=old["text"], proposed=old["text"],
                        final=current["text"], checks=[])
        db.flush()


# ----- check, export, save -----
def check(db: Session, row: Draft) -> dict[str, Any]:
    """Checks a draft: its format against Thông tư 68, its structure, and its wording against the style of its unit.

    Args:
        db: Database session.
        row: The draft.

    Returns:
        ``{"counts", "findings", "checked_at", "style"}``; the structure findings come first and are counted with the format
        findings.
    """
    content = content_of(row)
    unit_id = unit_of(db, row)
    result = check_draft(content)
    found = structure.check(content)
    result["findings"] = [*found, *result["findings"]]
    for item in found:
        result["counts"][item["severity"]] += 1
    guide = style.guide(organization.tree(), unit_id, content.template) if unit_id else {}
    body = "\n".join(block["text"] for block in content.blocks if block["kind"] != "table")
    result["style"] = {"wording": style_check.wording(body), "sections": style_check.sections(content, guide),
                       "blanks": style_check.blanks(content)}
    return result


def export(db: Session, row: Draft, folder: Path) -> Path:
    """Writes a draft as a .docx.

    Args:
        db: Database session.
        row: The draft.
        folder: Folder to write in.

    Returns:
        Path of the file, named after the draft's title.
    """
    content = content_of(row)
    issuer = issuer_of(unit_of(db, row), content.template)
    return render(content, folder / f"{slug(row.title or content.template.name)}.docx", issuer_name=issuer.name)


def save_to_store(db: Session, user: User, row: Draft, *, declared_secret: bool = False):
    """Saves the draft into the document store as a .docx, like an upload (it is indexed and placed by the usual rules)."""
    with tempfile.TemporaryDirectory(prefix="draft-") as folder:
        path = export(db, row, Path(folder))
        with path.open("rb") as stream:
            return documents.upload(db, user, filename=path.name, stream=stream, declared_secret=declared_secret)


__all__ = ["DraftContent", "catalogue", "check", "content_of", "create", "decide", "delete", "edit_table", "export", "find", "get",
           "propose",
           "resolve_unit", "save_to_store", "set_content", "set_fields", "set_style", "set_unit", "snapshot", "unit_of", "user_edit",
           "view"]
