"""How a unit writes, for the drafting assistant (`canvas_style`) and for the header a new draft starts with.

Two sources: the general rules of administrative writing in `style_rules.yaml` (Thông tư 68 and the conventions of the store,
reviewed by the staff), and the profile of each unit mined from its documents by `tools/build_style_profiles.py` (see
`app.drafting.style_mining`), read from DATA_DIR/style/profiles.json. Without that file the header falls back to the organisation
tree and the guide to the general rules.

A unit with few documents of a kind takes the layout and formulas (outline, openings, closings) and the terms of the nearest unit
above it that has enough; what names its own correspondents (bases cited, recipients, signers) comes from its own documents only.
"""
from __future__ import annotations

import dataclasses
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.core import config
from app.org import Scope, UnitTree
from app.search import QdrantIndex, SearchFilters

from . import style_mining
from .content import Issuer
from .templates import Template

MIN_KIND_DOCS = 5  # documents of a kind a unit needs before its own layout is used rather than its superior's
RULES_FILE = Path(__file__).with_name("style_rules.yaml")
_QUALIFIER = re.compile(r"\s*\([^)]*\)\s*$")  # "Ban Tài chính (Bộ Tham mưu)": the bracket only tells same-named units apart

_loaded: dict[str, Any] = {"stamp": None, "data": {}}


def profile_path() -> Path:
    """Where the unit profiles learned from the document store are kept."""
    return config.DATA_DIR / "style" / "profiles.json"


def profiles() -> dict[str, Any]:
    """The mined profiles, re-read when the file changes; {} when they have not been built (or were built by another version)."""
    path = profile_path()
    try:
        stamp = (str(path), path.stat().st_mtime_ns)
    except OSError:
        return {}
    if _loaded["stamp"] != stamp:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        _loaded.update(stamp=stamp, data=data if data.get("version") == style_mining.VERSION else {})
    return _loaded["data"]


@lru_cache(maxsize=1)
def _rules() -> dict[str, Any]:
    return yaml.safe_load(RULES_FILE.read_text(encoding="utf-8"))


def rules(template: Template) -> dict[str, Any]:
    """The general rules, the word choices and the conventions of `template`'s kind."""
    data = _rules()
    return {"source": data["source"], "general": data["general"], "words": data["words"], "kind": data["kinds"].get(template.kind, [])}


DEFAULT_CHOICE = {"preset": "don_vi", "detail": "vua"}


def options() -> dict[str, list[dict[str, str]]]:
    """The presets and detail levels the canvas offers, in the order of the rules file."""
    data = _rules()
    return {"presets": [{"id": key, "name": item["name"]} for key, item in data["presets"].items()],
            "detail": [{"id": key, "name": item["name"]} for key, item in data["detail"].items()]}


def choice(raw: dict[str, Any] | None) -> dict[str, str]:
    """A style choice checked against the rules file. An unknown preset or detail level falls back to the default."""
    data = _rules()
    raw = raw or {}
    preset = raw.get("preset") if raw.get("preset") in data.get("presets", {}) else DEFAULT_CHOICE["preset"]
    detail = raw.get("detail") if raw.get("detail") in data.get("detail", {}) else DEFAULT_CHOICE["detail"]
    return {"preset": preset, "detail": detail}


def is_default(raw: dict[str, Any] | None) -> bool:
    """Whether a draft's style choice is the default preset and level of detail."""
    return choice(raw) == DEFAULT_CHOICE


def _chosen(raw: dict[str, Any] | None) -> dict[str, Any]:
    """The chosen preset and detail level, with the rules the assistant must follow on top of the unit's profile."""
    data = _rules()
    picked = choice(raw)
    preset, detail = data["presets"][picked["preset"]], data["detail"][picked["detail"]]
    return {"preset": picked["preset"], "preset_name": preset["name"], "detail": picked["detail"], "detail_name": detail["name"],
            "rules": [*preset.get("rules", []), *detail.get("rules", [])]}


def _name(tree: UnitTree, unit_id: str) -> str:
    return _QUALIFIER.sub("", tree.get(unit_id).name)


def _default_issuer(tree: UnitTree, unit_id: str) -> str:
    """Without mined documents: a phòng or ban of an agency issues under the agency's name, anything else under its own."""
    unit = tree.get(unit_id)
    if unit.type in ("phong", "ban") and unit.parent and tree.get(unit.parent).type == "co_quan":
        return unit.parent
    return unit_id


def _kind(data: dict[str, Any], unit_id: str, template: Template) -> dict[str, Any]:
    return data.get("units", {}).get(unit_id, {}).get("kinds", {}).get(template.name, {})


def _issuing_part(symbol: str, template: Template) -> str:
    parts = [p for p in symbol.split("-") if p]
    return "" if len(parts) < 2 else parts[0] if template.kind == "CV" else parts[1]


_AUTHORITY = ("KT.", "TL.", "TUQ.", "TM.", "Q.")
_TITLE_END = ("TRƯỞNG", "LỆNH", "ỦY", "UỶ", "NHIỆM", "ĐỐC", "TỊCH", "THƯ")
_TITLE_START = ("PHÓ", "TRƯỞNG", "CHÁNH", "GIÁM", "CHỦ", "CỤC", "CHỈ", "TƯ", "HIỆU", "VIỆN", "CHÍNH", "BÍ")


def signer_lines(role: str) -> str:
    """Splits a signer's authority and title into the lines Thông tư 68 prints: the authority, then the signer's own title.

    Args:
        role: The authority and title on one line, as mined from documents.

    Returns:
        'KT. THAM MƯU TRƯỞNG\\nPHÓ THAM MƯU TRƯỞNG' for 'KT. THAM MƯU TRƯỞNG PHÓ THAM MƯU TRƯỞNG'; `role` unchanged when it has no
        authority prefix (KT., TL., TUQ., TM., Q.) or no recognisable second title.
    """
    words = role.split()
    if not words or words[0] not in _AUTHORITY:
        return role
    for i in range(2, len(words)):
        if words[i - 1] in _TITLE_END and words[i] in _TITLE_START:
            return " ".join(words[:i]) + "\n" + " ".join(words[i:])
    return role


def _signer(data: dict[str, Any], unit_id: str, issuer: str, template: Template) -> str:
    """The usual signer of a unit's documents of one kind.

    Args:
        data: The style profiles.
        unit_id: The drafting unit.
        issuer: The unit issuing its documents (consulted when the drafting unit has none of this kind).
        template: The kind of document.

    Returns:
        The most frequent authority and title, split into lines by `signer_lines`, when seen in at least two documents; else "".
    """
    for source in (unit_id, issuer):
        signers = _kind(data, source, template).get("signers") or []
        if signers and signers[0][1] >= 2:
            return signer_lines(signers[0][0])
    return ""


def issuer_for(tree: UnitTree, unit_id: str, template: Template, data: dict[str, Any] | None = None) -> Issuer:
    """The header a draft starts with, as the unit's recent documents of that kind (or of any kind) show it.

    Thông tư 68: a symbol is the kind and the issuing body ("KH-TM"); a công văn's is the issuing body and the drafting office
    ("TM-KHQS"). A blank part is left as "…" for the clerk.

    Args:
        tree: The unit tree.
        unit_id: The drafting unit.
        template: The kind of document.
        data: The style profiles; loaded from disk when None.

    Returns:
        The issuing body and its superior, the number symbol, the abbreviation of the "Lưu" line and the usual signer; an empty
        `Issuer` for an unknown unit.
    """
    if unit_id not in tree.units:
        return Issuer()
    data = profiles() if data is None else data
    mine, kind = data.get("units", {}).get(unit_id, {}), _kind(data, unit_id, template)
    issuer = (kind.get("issuer") if kind.get("docs", 0) >= MIN_KIND_DOCS else "") or mine.get("issuer") or ""
    if issuer not in tree.units:
        issuer = _default_issuer(tree, unit_id)
    parent = tree.get(issuer).parent
    known = data.get("issuers", {}).get(issuer, {})
    owner = _name(tree, parent) if parent else known.get("owner", "")
    abbr = known.get("abbr", "")
    symbol = kind.get("symbol", "") if kind.get("issuer") == issuer else ""
    if symbol and abbr and _issuing_part(symbol, template) != abbr:
        symbol = ""  # a one-off body ("QĐ-BTC" of an organising committee) is not the unit's usual symbol
    if not symbol and abbr:
        symbol = f"{abbr}-{mine.get('drafter') or mine.get('luu') or '…'}" if template.kind == "CV" else f"{template.kind}-{abbr}"
    return Issuer(_name(tree, issuer), owner, symbol, mine.get("luu", ""), _signer(data, unit_id, issuer, template))


def _formulas(items: list[list[Any]]) -> list[str]:
    return [f"{text}… ({n} văn bản)" for text, n in items]


def _outline(items: list[dict[str, Any]]) -> list[str]:
    return [f"{o['heading']} ({round(100 * o['share'])}% văn bản)" + (f": {'; '.join(o['sub'])}" if o["sub"] else "") for o in items]


def guide(tree: UnitTree, unit_id: str, template: Template, data: dict[str, Any] | None = None,
          choice: dict[str, Any] | None = None) -> dict[str, Any]:
    """What the assistant should follow when drafting `template` for a member of `unit_id`.

    `choice` is the preset and detail level the user picked on the canvas; its rules are added on top of the unit's profile and
    never replace the Thông tư 68 rules or the required parts of the kind."""
    data = profiles() if data is None else data
    out: dict[str, Any] = {"rules": rules(template)}
    if choice is not None:
        out["chosen"] = _chosen(choice)
    if unit_id not in tree.units:
        return out
    issuer = issuer_for(tree, unit_id, template, data)
    out["header"] = {"co_quan_chu_quan": issuer.parent.upper(), "co_quan_ban_hanh": issuer.name.upper(),
                     "so_ky_hieu": issuer.number_line(template.kind), "dong_luu": issuer.luu_line()}
    if not data.get("units"):
        out["note"] = "Chưa có hồ sơ văn phong học từ kho văn bản: theo quy tắc chung và văn bản mẫu (canvas_style có kèm)."
        return out
    chain = list(reversed(tree.path_to(unit_id)))
    source = next((n for n in chain if _kind(data, n, template).get("docs", 0) >= MIN_KIND_DOCS), None)
    if source:
        layout = _kind(data, source, template)
        out["based_on"] = f"{layout['docs']} {template.name.lower()} của {_name(tree, source)}" + (
            "" if source == unit_id else f" ({_name(tree, unit_id)} có ít {template.name.lower()} nên theo đơn vị cấp trên)")
        out["outline"] = _outline(layout.get("outline", []))
        out["openings"] = _formulas(layout.get("openings", []))
        out["closings"] = _formulas(layout.get("closings", []))
    own = _kind(data, unit_id, template)
    for key in ("bases", "recipients", "signers"):
        out[key] = [text for text, _ in own.get(key, [])]
    terms = next((data["units"][n]["terms"] for n in chain if data["units"].get(n, {}).get("terms")), [])
    out["terms"] = terms
    return {k: v for k, v in out.items() if v}


def choice_note(raw: dict[str, Any] | None) -> str:
    """The chosen preset and detail level as lines for a turn's prompt (not the whole unit profile)."""
    chosen = _chosen(raw)
    lines = [f"Người dùng chọn phong cách {chosen['preset_name']}, mức chi tiết {chosen['detail_name']}.",
             *(f"- {rule}" for rule in chosen["rules"]),
             "Phong cách này không được bỏ thành phần bắt buộc của loại văn bản hay quy tắc Thông tư 68."]
    return "\n".join(lines)


def prompt_note(tree: UnitTree, unit_id: str, template: Template, data: dict[str, Any] | None = None,
                choice: dict[str, Any] | None = None) -> str:
    """The style of `guide` as plain lines for the model's prompt (rules, word choices, the unit's usual formulas and terms), for
    a request that must follow it whether or not the model looks it up. `choice` appends the preset and detail level the user picked."""
    g = guide(tree, unit_id, template, data, choice)
    source = g.get("based_on") or f"quy tắc chung; chưa có hồ sơ văn phong của {_name(tree, unit_id) if unit_id in tree.units else 'đơn vị'}"
    lines = [f"Văn phong cần theo ({source}):", *(f"- {rule}" for rule in g["rules"]["general"] + g["rules"]["kind"])]
    for word in g["rules"]["words"]:
        lines.append(f"- Dùng '{word['use']}'" + (f", không dùng '{word['avoid']}'" if word.get("avoid") else "")
                     + (f": {word['note']}" if word.get("note") else "") + ".")
    for key, label in (("openings", "Câu mở đầu đơn vị hay dùng"), ("closings", "Câu kết đơn vị hay dùng")):
        if g.get(key):
            lines.append(f"- {label}: " + " | ".join(g[key]))
    if g.get("terms"):
        lines.append("- Thuật ngữ quen dùng của đơn vị: " + ", ".join(g["terms"]))
    if g.get("chosen"):
        lines.append(choice_note(g["chosen"]))
    return "\n".join(lines)


def _section_key(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"^[IVXL]{1,6}\s*[.:\-–]\s*", "", text.strip(), flags=re.IGNORECASE)).casefold()


def passage_of(found: style_mining.Sample, section: str) -> str:
    """The sample sentences under the heading closest to `section` ('' when the document has no such part)."""
    wanted = _section_key(section)
    if not wanted:
        return ""
    for heading, text in found.passages:
        key = _section_key(heading)
        if key == wanted or wanted in key or key in wanted:
            return text
    return ""


def examples(index: QdrantIndex, scope: Scope, template: Template, topic: str = "", limit: int = 3, section: str = "") -> list[dict[str, Any]]:
    """Documents of `template`'s kind closest to `topic` that the user may read (ordinary ones only, never secret): how each opens,
    is laid out and closes, for the assistant to imitate the style, not the content. With `section`, each one also carries the
    opening sentences of that part."""
    readable = dataclasses.replace(scope, levels=scope.levels & {"thuong"})
    if not readable.levels:
        return []
    hits = index.search(topic.strip() or template.name, readable, k=limit * 8, filters=SearchFilters(doc_types=[template.name]))
    out: list[dict[str, Any]] = []
    for doc_id in dict.fromkeys(h.doc_id for h in hits):
        chunks = index.get_chunks(doc_id, readable)
        found = style_mining.sample(chunks)
        if found is None or not (found.opening or found.outline):
            continue
        meta = chunks[0]
        number = f"{meta.get('number', '')}/{meta.get('symbol', '')}".strip("/")
        out.append({k: v for k, v in {
            "doc": f"{meta.get('doc_type', '')} {number} {(meta.get('date') or '')[:10]}: {meta.get('title', '')}".replace("  ", " "),
            "bases": found.bases[:3],
            "opening": found.opening,
            "outline": [h + (f": {'; '.join(subs)}" if subs else "") for h, subs in found.outline],
            "closing": found.closing,
            "passage": passage_of(found, section),
        }.items() if v})
        if len(out) == limit:
            break
    return out
