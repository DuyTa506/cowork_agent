from __future__ import annotations
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .models import Metadata, ParsedDocument, Section
from .structure import _RANK

# Sizes are in whitespace-separated words, which for Vietnamese are syllables (about 1.5-2 model tokens each).
@dataclass(frozen=True)
class ChunkConfig:
    target: int = 220  # close a chunk once it holds about this many words
    max: int = 380  # never exceed this (except one unsplittable sentence)
    min: int = 60  # smaller chunks are merged into a neighbour
    hard_rank: int = 5  # sections up to this rank (Phần, Chương, Mục, Điều, I., A.) start a new chunk when the current one is big enough
    heading_chars: int = 90  # breadcrumb entries are cut to this length

@dataclass
class Chunk:
    doc_id: str
    index: int
    part: str  # meta | preamble | body
    path: list[str]  # headings from the top down to the (common) section of the chunk
    text: str
    context: str  # one line identifying the document, prepended for embedding
    words: int
    pi_first: int = -1  # source paragraph range, to highlight the passage in the original
    pi_last: int = -1

    @property
    def id(self) -> str:
        return f"{self.doc_id}#{self.index}"

    @property
    def embed_text(self) -> str:
        head = " > ".join(self.path)
        return "\n".join(x for x in (self.context, head, self.text) if x)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "id": self.id}

@dataclass
class _Atom:
    text: str
    words: int
    rank: int
    path: list[str]
    part: str
    pi_first: int
    pi_last: int
    kinds: set[str] = field(default_factory=set)

def count_words(text: str) -> int:
    return len(text.split())

_SENT = re.compile(r"(?<=[.;!?])\s+")

def _split_text(text: str, limit: int) -> list[str]:
    """Splits one long paragraph on sentence ends, packing sentences up to `limit` words."""
    out: list[str] = []
    cur: list[str] = []
    n = 0
    for sent in _SENT.split(text):
        w = count_words(sent)
        if w > limit:  # a sentence longer than the limit: cut by words
            if cur:
                out.append(" ".join(cur)); cur, n = [], 0
            words = sent.split()
            out += [" ".join(words[i:i + limit]) for i in range(0, len(words), limit)]
            continue
        if n + w > limit and cur:
            out.append(" ".join(cur)); cur, n = [], 0
        cur.append(sent); n += w
    if cur:
        out.append(" ".join(cur))
    return out

def _split_table(text: str, limit: int) -> list[str]:
    """Splits a table by rows. A short first row (the column heads) is repeated at the top of each piece; a long one is
    data, not heads, and is not repeated. A single row longer than the limit is cut like a paragraph."""
    rows = text.split("\n")
    repeat = count_words(rows[0]) <= limit // 4
    base = [rows[0]] if repeat else []
    out: list[str] = []
    cur = list(base)
    n = sum(count_words(r) for r in cur)

    def flush() -> None:
        if len(cur) > len(base):
            out.append("\n".join(cur))

    for row in rows[1:] if repeat else rows:
        w = count_words(row)
        if w > limit:
            flush()
            out += _split_text(row, limit)
            cur, n = list(base), sum(count_words(r) for r in base)
            continue
        if n + w > limit and len(cur) > len(base):
            flush()
            cur, n = list(base), sum(count_words(r) for r in base)
        cur.append(row); n += w
    flush()
    return out or [text]

def _block_parts(kind: str, text: str, limit: int) -> list[str]:
    if count_words(text) <= limit:
        return [text]
    return _split_table(text, limit) if kind == "table" else _split_text(text, limit)

def _atoms(sec: Section, ancestors: list[str], cfg: ChunkConfig, out: list[_Atom]) -> None:
    """Depth-first, document order: one or more atoms per section holding its own heading and blocks (not its children's)."""
    is_root = sec.kind == "root"
    path = ancestors if is_root else ancestors + [sec.heading[:cfg.heading_chars]]
    rank = _RANK.get(sec.kind, 6)
    part = "preamble" if is_root else "body"
    pieces: list[tuple[str, str, int]] = []  # (text, kind, pi)
    if sec.heading:  # a numbered paragraph is its own heading, so a long one has to be cut too
        pieces += [(t, "heading", sec.pi) for t in _block_parts("heading", sec.heading, cfg.target)]
    for b in sec.blocks:
        for t in _block_parts(b.kind, b.text, cfg.target):
            pieces.append((t, b.kind, b.pi))
    group: list[tuple[str, str, int]] = []
    n = 0
    first = True
    for piece in pieces + [None]:  # type: ignore[list-item]
        flush = piece is None or (group and n + count_words(piece[0]) > cfg.max)
        if flush and group:
            text = "\n".join(t for t, _, _ in group)
            out.append(_Atom(text, count_words(text), rank if first else 6, path, part, group[0][2], group[-1][2],
                             {k for _, k, _ in group}))
            first, group, n = False, [], 0
        if piece is not None:
            group.append(piece); n += count_words(piece[0])
    for child in sec.children:
        _atoms(child, path, cfg, out)

def _common_prefix(paths: list[list[str]]) -> list[str]:
    first = paths[0]
    n = 0
    for i, h in enumerate(first):
        if all(len(p) > i and p[i] == h for p in paths):
            n = i + 1
        else:
            break
    return first[:n]

def _fmt_date(meta: Metadata) -> str:
    if meta.date:
        y, m, d = meta.date.split("-")
        return f"{int(d)}/{int(m)}/{y}"
    return ""

def doc_context(meta: Metadata) -> str:
    """One line that says which document a passage comes from, e.g. 'Quyết định 15/QĐ-QK3 (1/10/2026) - Quân khu 3 - Về việc ...'."""
    ident = " ".join(x for x in (meta.doc_type, f"{meta.number}/{meta.symbol}" if meta.number and meta.symbol else meta.symbol) if x)
    date = _fmt_date(meta)
    parts = [ident + (f" ({date})" if date else ""), meta.issuing_agency, meta.title[:160]]
    return " - ".join(p for p in parts if p)

def meta_card(meta: Metadata) -> str:
    """The document's identity as plain sentences, so questions like 'who signed' or 'sent to whom' find a passage."""
    lines = []
    ident = " ".join(x for x in (meta.doc_type, f"số {meta.number}/{meta.symbol}" if meta.number and meta.symbol else meta.symbol) if x)
    if ident:
        lines.append(ident + (f", ngày {_fmt_date(meta)}" if meta.date else (f", {meta.date_text}" if meta.date_text else "")))
    if meta.issuing_agency:
        lines.append("Cơ quan ban hành: " + (f"{meta.parent_agency} - " if meta.parent_agency else "") + meta.issuing_agency)
    if meta.subject or meta.title:
        lines.append("Trích yếu: " + (meta.subject or meta.title))
    if meta.recipients_to:
        lines.append("Kính gửi: " + "; ".join(meta.recipients_to))
    if meta.signer_name:
        lines.append("Người ký: " + " ".join(x for x in (meta.signer_role, meta.signer_name) if x))
    if meta.distribution:
        lines.append("Nơi nhận: " + "; ".join(meta.distribution))
    return "\n".join(lines)

def chunk_document(doc: ParsedDocument, doc_id: str, cfg: ChunkConfig | None = None) -> list[Chunk]:
    cfg = cfg or ChunkConfig()
    context = doc_context(doc.metadata)
    atoms: list[_Atom] = []
    _atoms(doc.root, [], cfg, atoms)

    chunks: list[Chunk] = []

    def emit(group: list[_Atom]) -> None:
        text = "\n".join(a.text for a in group)
        part = "preamble" if all(a.part == "preamble" for a in group) else "body"
        chunks.append(Chunk(doc_id, len(chunks), part, _common_prefix([a.path for a in group]), text, context,
                            count_words(text), group[0].pi_first, group[-1].pi_last))

    card = meta_card(doc.metadata)
    if card:
        chunks.append(Chunk(doc_id, 0, "meta", [], card, context, count_words(card)))

    cur: list[_Atom] = []
    size = 0
    for a in atoms:
        if cur:
            if a.rank <= cfg.hard_rank and size >= cfg.min:
                emit(cur); cur, size = [], 0
            elif size + a.words > cfg.target and size >= cfg.min:
                emit(cur); cur, size = [], 0
            elif size + a.words > cfg.max:
                emit(cur); cur, size = [], 0
        cur.append(a); size += a.words
    if cur:
        # a short tail joins the previous body chunk rather than standing alone
        tail_words = size
        prev = chunks[-1] if chunks and chunks[-1].part != "meta" else None
        if prev is not None and tail_words < cfg.min and prev.words + tail_words <= cfg.max:
            text = "\n".join(a.text for a in cur)
            prev.text += "\n" + text
            prev.words += tail_words
            prev.pi_last = cur[-1].pi_last
            prev.path = _common_prefix([prev.path, _common_prefix([a.path for a in cur])])
            prev.part = "body" if prev.part == "body" or any(a.part == "body" for a in cur) else prev.part
        else:
            emit(cur)
    return chunks
