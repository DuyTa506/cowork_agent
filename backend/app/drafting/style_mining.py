"""Learns how each unit writes from the documents in the store, for the drafting assistant (read back by `app.drafting.style`).

A *sample* is what one indexed document shows about its style, read from its chunks in the search index: the meta card gives the
issuing body, the signer and the recipients (with the "Lưu" line); the other chunks give the bases cited, the opening and closing
sentences and the outline (top-level headings "I. ...", each with its numbered sub-headings). Appendices are left out.

`build` turns the samples into one profile per unit of the organisation (a unit's profile covers the documents of its subtree) and,
inside it, one per kind of document. Three rules keep a profile from carrying the content of particular documents:

* secret documents are left out;
* an item (heading, formula, basis, recipient, signer, term) enters a profile only when at least `MIN_DF` documents share it;
* in the profile of a unit with several units below it, an outline heading, formula or term must also come from at least two of
  those units, so that what one office repeats (a daily bulletin) does not become the convention of the whole agency.

The header a unit issues under (issuing body, number symbol, "Lưu" line) follows its most recent documents, so a renamed agency
("Cục Hậu cần" -> "Cục Hậu cần - Kỹ thuật") wins over the older, more numerous documents. The issuing body is read from the number
symbol rather than from the agency line, which the parser sometimes takes from the superior body ("QUÂN KHU 3" above "BỘ THAM MƯU").
"""
from __future__ import annotations

import itertools
import math
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Callable, Iterable

from app.org import UnitTree

VERSION = 1
MIN_DF = 3
MIN_SHARE = 0.2  # share of a kind's documents that must have a heading for it to be in the outline
HALF_LIFE_DAYS = 365  # a document a year older than the newest counts half as much for the header a unit uses now
UNDATED_WEIGHT = 0.25
MIN_SUPPORT = 2  # documents a header value needs to beat the others, however recent (one odd document does not decide)
GRAM_SIZES = (3, 4, 5)
FORMULA_TOKENS = 32  # words and marks of a sentence opening considered ("Thực hiện Kế hoạch số …/KH-QK3 ngày … của ...")
FRAGMENT_SHARE = 0.6  # a phrase the same word precedes or follows this often is part of a longer one
CV = "Công văn"
TOP = {"outline": 10, "sub": 6, "formulas": 5, "bases": 6, "recipients": 10, "signers": 3, "terms": 20}
PASSAGE_CHARS = 400  # first sentences kept under a heading, for an example of how that part is written

_LATEX = re.compile(r"\$([^$]{0,40})\$")
_MARKDOWN = re.compile(r"(?:^|(?<=\s))#{1,6}(?=\s|$)|\*\*")
_SPACE = re.compile(r"\s+")
_ROMAN = re.compile(r"^([IVXL]{1,6})\s*[.:\-–]\s*(\S.*)$")
_NUMBERED = re.compile(r"^(\d{1,2})\s*[.)]\s*(\S.*)$")
_RANK = re.compile(r"\b(?:Đại|Thượng|Trung|Thiếu)\s+(?:tướng|tá|úy|uý)\b|\b(?:Hạ sĩ|Trung sĩ|Thượng sĩ)\b")
_LUU = re.compile(r"^Lưu\s*:?\s*(.*)$", re.IGNORECASE)
_LUU_UNIT = re.compile(r"\bVT\s*[,.]\s*([^\s.;,(]+)")
_YEAR = re.compile(r"\bnăm\s+((?:19|20)\d{2})\b|\b\d{1,2}/\d{1,2}/((?:19|20)\d{2})\b")
# numbers that change from one document to the next (document numbers, dates, years), not those in names ("Quân khu 3")
_NUMBERS = re.compile(r"\d+(?:[/.\-]\d+)+|(?<=\bsố )\d+|(?<=\bngày )\d+|(?<=\btháng )\d+|(?<=\bnăm )\d+|\b(?:19|20)\d{2}\b")
_GLUED_DASH = re.compile(r"(?<=\w)[-–]\s+(?=\w)")
_END_MARK = re.compile(r"\s*\.?/\.?\s*$")
_BREAK = re.compile(r"[^\w\s]|\d|_")
_TOKEN = re.compile(r"\w+|[^\w\s]")
_STOP = frozenset("và của các những được cho với theo trong tại là có để về từ đến này đó khi thì một như do bằng sau trên dưới "
                  "đã sẽ đang không cũng hoặc nhằm ra vào lại số ngày tháng năm".split())
_LOOSE_LETTER = re.compile(r"(?<!\S)[A-ZĐ](?!\S)")  # a stamp or OCR letter inside the signer's title ("THAM MƯU TRƯỞNG M PHÓ ...")
_SIGNATURE = ("KT.", "TM.", "TL.", "TUQ.", "Q.", "Nơi nhận", "Lưu")
_ITEM = ("-", "+", "•", "*", "…")
_APPENDIX = re.compile(r"^\(?\s*Kèm theo\b|^PHỤ LỤC\b|^Phụ lục\s+[IVX\d]", re.IGNORECASE)


def clean(text: str) -> str:
    """NFC text without OCR markup ('$^{(07)}$' -> '(07)'; a stray '$\\mathcal{O}$', '##' or '**' goes) and with spaces collapsed."""
    def latex(match: re.Match[str]) -> str:
        inner = re.sub(r"\\[a-zA-Z]+|[{}^_\\]", "", match.group(1))
        return inner if re.search(r"\d", inner) else ""
    text = _MARKDOWN.sub(" ", _LATEX.sub(latex, unicodedata.normalize("NFC", text or "")))
    return _SPACE.sub(" ", text).strip()


def _upper_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    return sum(c.isupper() for c in letters) / len(letters) if letters else 0.0


def _heading(text: str) -> str:
    return re.sub(r"\s+([,;:])", r"\1", _GLUED_DASH.sub(", ", text)).strip().rstrip(" .:;")


def _is_title(text: str) -> bool:
    """A numbered line that names a part ('1. Mục đích', '2. Phòng Tác chiến:') rather than a numbered sentence or item."""
    return len(text.split()) <= 10 and not text.rstrip().endswith((";", ".", ",")) and text[:1].isupper()


def _is_sentence(line: str) -> bool:
    """A line of running text that starts a sentence: no heading, list item, table row, line in capitals or the rest of a
    sentence broken over two lines."""
    return (len(line.split()) >= 6 and line[:1].isupper() and _upper_ratio(line) < 0.5 and not _ROMAN.match(line)
            and not _NUMBERED.match(line) and not line.startswith(_ITEM) and " | " not in line)


@dataclass
class Sample:
    """What one document shows about its unit's style."""

    doc_id: str
    unit_id: str
    kind: str
    date: str = ""
    symbol: str = ""
    issuing_agency: str = ""
    parent_agency: str = ""
    signer_role: str = ""
    recipients: list[str] = field(default_factory=list)
    luu: str = ""
    bases: list[str] = field(default_factory=list)
    opening: str = ""
    closing: str = ""
    outline: list[tuple[str, list[str]]] = field(default_factory=list)
    passages: list[tuple[str, str]] = field(default_factory=list)  # (heading, first sentences); read at query time, not stored in a profile
    text: str = ""
    issuer: str = ""  # unit id of the issuing body, set by `build`

    @property
    def symbol_parts(self) -> tuple[str, str]:
        """(issuing body, drafting office) abbreviations of the symbol: 'TM-KHQS' of a công văn -> ('TM', 'KHQS'); 'KH-TM' -> ('TM', '')."""
        parts = [p for p in self.symbol.replace("–", "-").split("-") if p]
        if len(parts) < 2:
            return "", ""
        return (parts[0], parts[1]) if self.kind == CV else (parts[1], "")


def sample(chunks: list[dict[str, Any]], *, keep_secret: bool = False) -> Sample | None:
    """The style sample of one document from its chunk payloads; None when it has no kind, or is secret (unless `keep_secret`)."""
    if not chunks:
        return None
    chunks = sorted(chunks, key=lambda c: c.get("chunk_index", 0))
    head = chunks[0]
    if not head.get("doc_type") or (head.get("level", "thuong") != "thuong" and not keep_secret):
        return None
    out = Sample(str(head["doc_id"]), head.get("unit_id", ""), head["doc_type"], (head.get("date") or "")[:10],
                 clean(head.get("symbol", "")), clean(head.get("issuing_agency", "")))
    lines: list[str] = []
    for chunk in chunks:
        if chunk.get("part") == "meta":
            _read_card(out, chunk.get("text", ""))
        else:
            lines += [line for line in (clean(x) for x in chunk.get("text", "").splitlines()) if line]
    # appendices ("(Kèm theo Kế hoạch số ...)", tables of figures) follow the body and are not part of its style
    lines = lines[:next((i for i, line in enumerate(lines) if i and _APPENDIX.match(line)), len(lines))]
    _read_body(out, lines)
    out.text = "\n".join(line for line in lines if " | " not in line)
    return out


def _role(signer: str) -> str:
    """The signer's authority and title without rank and name ('KT. THAM MƯU TRƯỞNG PHÓ THAM MƯU TRƯỞNG Thiếu tướng X' -> the first part)."""
    match = _RANK.search(signer)
    if match:
        role = signer[:match.start()]
    else:
        role = " ".join(itertools.takewhile(lambda w: _upper_ratio(w) > 0.9 or not any(c.isalpha() for c in w), signer.split()))
    return _SPACE.sub(" ", _LOOSE_LETTER.sub(" ", role)).strip(" ,.;:")


def _read_card(out: Sample, card: str) -> None:
    lines = card.splitlines()
    if not out.date and lines:
        # no full date (a blank day or month): the year of the date line still tells how recent the document is
        year = _YEAR.search(lines[0])
        out.date = f"{year.group(1) or year.group(2)}-07-01" if year else ""
    for line in lines:
        label, _, value = line.partition(": ")
        value = clean(value)
        if label == "Cơ quan ban hành" and out.issuing_agency and value.endswith(out.issuing_agency):
            out.parent_agency = value[:-len(out.issuing_agency)].strip(" -")
        elif label == "Người ký":
            out.signer_role = _role(value)
        elif label == "Nơi nhận":
            for item in value.split(";"):
                item = item.strip(" -+•*")
                luu = _LUU.match(item)
                if luu:
                    unit = _LUU_UNIT.search(luu.group(1))
                    out.luu = unit.group(1) if unit else out.luu
                elif re.search(r"\w", item):
                    out.recipients.append(item.rstrip(" ."))


def _read_body(out: Sample, lines: list[str]) -> None:
    section: tuple[str, list[str]] | None = None
    grabbed: list[str] = []

    def close() -> None:
        if section is None or not grabbed:
            return
        text = " ".join(grabbed)
        if len(text) > PASSAGE_CHARS:
            text = text[:PASSAGE_CHARS].rsplit(" ", 1)[0]
        out.passages.append((section[0], text))

    for line in lines:
        top = _ROMAN.match(line)
        if top and _upper_ratio(top.group(2)) >= 0.6 and len(top.group(2).split()) <= 14:
            close()
            grabbed = []
            section = (_heading(top.group(2)).upper(), [])
            out.outline.append(section)
            continue
        sub = _NUMBERED.match(line)
        if section is not None and sub and _is_title(sub.group(2)):
            section[1].append(_heading(sub.group(2)))
            continue
        if section is not None and len(grabbed) < 2 and _is_sentence(line):
            grabbed.append(_END_MARK.sub("", line))
            continue
        if section is None and line.startswith("Căn cứ"):
            out.bases.append(line.rstrip(" ;."))
        elif section is None and not out.opening and _is_sentence(line) and not line.startswith(("Kính gửi", "Đồng kính gửi")):
            out.opening = line
    close()
    out.closing = _END_MARK.sub("", next((l for l in reversed(lines) if _is_sentence(l) and not l.startswith(_SIGNATURE)), ""))


# ----- building the profiles -----
def _day(text: str) -> date | None:
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _recent(samples: list[Sample], value: Callable[[Sample], str]) -> str:
    """The value most documents use, each weighted by how recent it is (halved per `HALF_LIFE_DAYS` before the newest document;
    `UNDATED_WEIGHT` without a date); ties go to the most recent. Only values at least `MIN_SUPPORT` documents use compete,
    when there are any."""
    pairs = sorted(((_day(s.date), v) for s in samples if (v := value(s))), key=lambda p: p[0] or date.min, reverse=True)
    if not pairs:
        return ""
    counts = Counter(v for _, v in pairs)
    if max(counts.values()) >= MIN_SUPPORT:
        pairs = [(day, v) for day, v in pairs if counts[v] >= MIN_SUPPORT]
    newest = pairs[0][0]
    weights: Counter[str] = Counter()
    for day, v in pairs:
        weights[v] += 0.5 ** ((newest - day).days / HALF_LIFE_DAYS) if newest and day else UNDATED_WEIGHT
    best = max(weights.values())
    return next(v for _, v in pairs if weights[v] == best)


class _Tally:
    """How many documents, and from how many units, show each item."""

    def __init__(self) -> None:
        self.docs: Counter[str] = Counter()
        self.units: dict[str, set[str]] = defaultdict(set)

    def add(self, unit: str, items: Iterable[str]) -> None:
        for item in set(items):
            self.docs[item] += 1
            self.units[item].add(unit)

    def shared(self, item: str, spread: int, floor: float = MIN_DF) -> bool:
        return self.docs[item] >= max(MIN_DF, floor) and len(self.units[item]) >= spread

    def top(self, limit: int, spread: int = 1) -> list[list[Any]]:
        return [[item, n] for item, n in self.docs.most_common() if self.shared(item, spread)][:limit]


def _spread(samples: list[Sample]) -> int:
    """How many units must share an item before it counts as the convention of this group: two when it spans several units."""
    return 2 if len({s.unit_id for s in samples}) > 1 else 1


def _outline(samples: list[Sample], spread: int) -> list[dict[str, Any]]:
    """Top-level headings that at least `MIN_SHARE` of the documents have, in their usual order, with their usual sub-headings."""
    heads, subs = _Tally(), defaultdict(_Tally)
    places: dict[str, list[float]] = defaultdict(list)
    sub_places: dict[tuple[str, str], list[int]] = defaultdict(list)
    for s in samples:
        sections: dict[str, list[str]] = {}
        for head, children in s.outline:
            sections.setdefault(head, []).extend(c for c in children if c not in sections.get(head, []))
        heads.add(s.unit_id, sections)
        for index, (head, children) in enumerate(sections.items()):
            places[head].append(index / max(1, len(sections) - 1))
            subs[head].add(s.unit_id, children)
            for position, child in enumerate(children):
                sub_places[head, child].append(position)
    keep = [h for h in heads.docs if heads.shared(h, spread, MIN_SHARE * len(samples))]
    keep.sort(key=lambda h: statistics.mean(places[h]))
    out = []
    for head in keep[:TOP["outline"]]:
        children = [c for c, _ in subs[head].top(TOP["sub"], spread) if subs[head].docs[c] >= 0.3 * heads.docs[head]]
        children.sort(key=lambda c: statistics.mean(sub_places[head, c]))
        out.append({"heading": head, "share": round(heads.docs[head] / len(samples), 2), "sub": children})
    return out


def _formulas(items: list[tuple[str, str]], spread: int) -> list[list[Any]]:
    """Sentence openings several documents share ('Nhận được kế hoạch, đề nghị các cơ quan, đơn vị'), numbers masked: the longest
    shared prefix of each family, most used first. `items` are (unit, sentence). Prefixes end at a word or mark and are counted
    without regard to case or dash ("Nhận được Kế hoạch" = "Nhận được kế hoạch"), shown in their most used spelling."""
    tally = _Tally()
    spellings: dict[str, Counter[str]] = defaultdict(Counter)
    for unit, text in items:
        text = _NUMBERS.sub("…", text)
        prefixes = [text[:m.end()] for m in itertools.islice(_TOKEN.finditer(text), FORMULA_TOKENS)][3:]
        keys = [p.lower().replace("–", "-") for p in prefixes]
        tally.add(unit, keys)
        for key, prefix in zip(keys, prefixes):
            spellings[key][prefix] += 1
    frequent = {p: n for p, n in tally.docs.items() if tally.shared(p, spread)}
    # the longest prefix of a family: one that no longer prefix extends in 80% of its documents
    longest = [p for p, n in frequent.items() if not any(len(q) > len(p) and q.startswith(p) and m >= 0.8 * n for q, m in frequent.items())]
    longest.sort(key=lambda p: (-frequent[p], -len(p)))
    out: list[list[Any]] = []
    for key in longest:
        text = spellings[key].most_common(1)[0][0].rstrip(" ,;:")
        if not any(text.lower() in t.lower() or t.lower() in text.lower() for t, _ in out):
            out.append([text, frequent[key]])
        if len(out) == TOP["formulas"]:
            break
    return out


def _positions(text: str) -> Iterable[tuple[str, str, str]]:
    """(phrase, word before, word after) for every candidate phrase of `text`: 3 to 5 words inside one clause, not starting or
    ending with a function word; a neighbour is '' at the edge of the clause or when it is a function word."""
    for segment in _BREAK.split(text.lower()):
        words = segment.split()
        for n in GRAM_SIZES:
            for i in range(len(words) - n + 1):
                if words[i] not in _STOP and words[i + n - 1] not in _STOP:
                    before = words[i - 1] if i and words[i - 1] not in _STOP else ""
                    after = words[i + n] if i + n < len(words) and words[i + n] not in _STOP else ""
                    yield " ".join(words[i:i + n]), before, after


def _grams(text: str) -> set[str]:
    return {gram for gram, _, _ in _positions(text)}


def _fragments(items: list[Sample], grams: set[str]) -> set[str]:
    """Phrases nearly always part of a longer one: the same word precedes or follows them in `FRAGMENT_SHARE` of their uses
    ('lượng vũ trang quân khu' inside 'lực lượng vũ trang quân khu', 'định có hiệu lực kể' inside 'quyết định ...')."""
    uses: Counter[str] = Counter()
    before: dict[str, Counter[str]] = defaultdict(Counter)
    after: dict[str, Counter[str]] = defaultdict(Counter)
    for s in items:
        for gram, left, right in _positions(s.text):
            if gram in grams:
                uses[gram] += 1
                before[gram][left] += bool(left)
                after[gram][right] += bool(right)
    return {g for g in grams if any(max(c.values(), default=0) >= FRAGMENT_SHARE * uses[g] for c in (before[g], after[g]))}


def _pairs(gram: str) -> set[tuple[str, str]]:
    words = gram.split()
    return set(zip(words, words[1:]))


def _terms(groups: dict[str, list[Sample]], everything: list[Sample]) -> dict[str, list[str]]:
    """Phrases that set a unit apart: shared by at least a tenth of its documents (and, for a group of units, by two of them) and
    at least twice as common there as in the whole store. Fragments of longer phrases are left out."""
    candidates: dict[str, Counter[str]] = {}
    for node, items in groups.items():
        if len(items) < 2 * MIN_DF or len(items) == len(everything):
            continue
        counts: Counter[str] = Counter()
        for s in items:
            counts.update(_grams(s.text))
        floor = max(MIN_DF, 0.1 * len(items))
        kept = Counter({g: n for g, n in counts.items() if n >= floor})
        if _spread(items) > 1:
            units: dict[str, set[str]] = defaultdict(set)
            for s in items:
                for g in _grams(s.text) & kept.keys():
                    units[g].add(s.unit_id)
            kept = Counter({g: n for g, n in kept.items() if len(units[g]) > 1})
        fragments = _fragments(items, set(kept))
        candidates[node] = Counter({g: n for g, n in kept.items() if g not in fragments})
    wanted = set().union(*candidates.values()) if candidates else set()
    overall: Counter[str] = Counter()
    for s in everything:
        overall.update(_grams(s.text) & wanted)
    out: dict[str, list[str]] = {}
    for node, counts in candidates.items():
        size = len(groups[node])
        scored = []
        for gram, n in counts.items():
            lift = (n / size) / (overall[gram] / len(everything))
            if lift >= 2:
                scored.append((n * math.log(lift), gram))
        chosen: list[str] = []
        for _, gram in sorted(scored, reverse=True):
            # skip a fragment of a phrase already chosen ('phòng khoa học quân' after 'khoa học quân sự')
            if not any(len(_pairs(gram) & _pairs(c)) >= 2 for c in chosen):
                chosen.append(gram)
            if len(chosen) == TOP["terms"]:
                break
        if chosen:
            out[node] = chosen
    return out


def _kind_profile(node: str, samples: list[Sample], allowed: set[str]) -> dict[str, Any]:
    spread = _spread(samples)
    issued = [s for s in samples if s.issuer in allowed]
    issuer = _recent(issued, lambda s: s.issuer)
    # a công văn's symbol names the drafting office, so only the unit's own công văn show the symbol it should use
    own = [s for s in issued if s.issuer == issuer and (s.kind != CV or s.unit_id == node)]
    tallies = {name: _Tally() for name in ("bases", "recipients", "signers")}
    for s in samples:
        tallies["bases"].add(s.unit_id, s.bases)
        tallies["recipients"].add(s.unit_id, s.recipients)
        tallies["signers"].add(s.unit_id, [s.signer_role] if s.signer_role else [])
    entry = {
        "docs": len(samples), "issuer": issuer, "symbol": _recent(own, lambda s: s.symbol),
        "outline": _outline(samples, spread),
        "openings": _formulas([(s.unit_id, s.opening) for s in samples if s.opening], spread),
        "closings": _formulas([(s.unit_id, s.closing) for s in samples if s.closing], spread),
        **{name: tally.top(TOP[name]) for name, tally in tallies.items()},
    }
    return {k: v for k, v in entry.items() if v}


def _assign_issuers(samples: list[Sample], tree: UnitTree) -> None:
    """Sets each sample's issuing body from the abbreviation in its symbol ("TM" -> Bộ Tham mưu), as the documents whose agency
    line names a unit vote it; an abbreviation several bodies share ("TĐ" for every battalion) is read by the votes of the
    document's own unit. Without a symbol, the agency line decides."""
    named = {s.doc_id: (tree.resolve_header(s.issuing_agency).unit_id or "") if s.issuing_agency else "" for s in samples}
    votes: dict[str, Counter[str]] = defaultdict(Counter)
    local: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for s in samples:
        part = s.symbol_parts[0]
        if part and named[s.doc_id]:
            votes[part][named[s.doc_id]] += 1
            local[s.unit_id, part][named[s.doc_id]] += 1
    for s in samples:
        part = s.symbol_parts[0]
        mine, everyone = local.get((s.unit_id, part), Counter()), votes.get(part, Counter())
        if mine and mine.most_common(1)[0][1] >= 0.6 * sum(mine.values()):
            s.issuer = mine.most_common(1)[0][0]
        elif everyone and everyone.most_common(1)[0][1] >= max(MIN_DF, 0.6 * sum(everyone.values())):
            s.issuer = everyone.most_common(1)[0][0]
        else:
            s.issuer = named[s.doc_id]


def build(samples: Iterable[Sample], tree: UnitTree) -> dict[str, Any]:
    """Profiles of every unit (over its subtree) and kind of document, plus the abbreviation and superior body of each issuing body."""
    samples = [s for s in samples if s.unit_id in tree.units]
    _assign_issuers(samples, tree)
    by_issuer: dict[str, list[Sample]] = defaultdict(list)
    for s in samples:
        if s.issuer:
            by_issuer[s.issuer].append(s)
    issuers = {unit: {k: v for k, v in {"abbr": _recent(items, lambda s: s.symbol_parts[0]),
                                        "owner": _recent(items, lambda s: s.parent_agency)}.items() if v}
               for unit, items in by_issuer.items()}

    groups: dict[str, list[Sample]] = defaultdict(list)
    for s in samples:
        for node in tree.path_to(s.unit_id):
            groups[node].append(s)
    terms = _terms(groups, samples)
    units: dict[str, Any] = {}
    for node, items in groups.items():
        allowed = {node, *tree.ancestors(node)}
        own = [s for s in items if s.unit_id == node]
        kinds: dict[str, list[Sample]] = defaultdict(list)
        for s in items:
            kinds[s.kind].append(s)
        entry = {
            "docs": len(items),
            "issuer": _recent([s for s in items if s.issuer in allowed], lambda s: s.issuer),
            "luu": _recent(own, lambda s: s.luu),
            "drafter": _recent([s for s in own if s.kind == CV and s.issuer in allowed], lambda s: s.symbol_parts[1]),
            "terms": terms.get(node, []),
            "kinds": {kind: _kind_profile(node, ks, allowed) for kind, ks in sorted(kinds.items())},
        }
        units[node] = {k: v for k, v in entry.items() if v}
    return {"version": VERSION, "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "documents": len(samples),
            "issuers": {k: v for k, v in issuers.items() if v}, "units": units}
