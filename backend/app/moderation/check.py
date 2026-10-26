"""Matching of the lexicon against a message."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

LEXICON = Path(__file__).with_name("lexicon.yaml")
CATEGORY_LABELS = {"tuc": "chửi thề, thô tục", "xuc_pham": "xúc phạm", "ky_thi": "kỳ thị", "de_doa": "đe dọa"}
EXCERPT = 40  # characters kept on each side of a match for the audit trail

_STRETCH = re.compile(r"(.)\1{2,}")  # three or more of the same character: someone leaning on the key
# Characters people put between the letters of a word to hide it: "đ.m", "d_i_t", "đ-m". A "*" stands for one hidden letter ("đ*t").
_SEPARATORS = re.compile(r"[._\-+~^|/\\'`\"]+")
_LEET = str.maketrans({"@": "a", "$": "s", "0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "!": "i"})


@dataclass(frozen=True)
class Hit:
    term: str
    category: str
    severity: str  # nhe | nang
    excerpt: str


@dataclass
class Verdict:
    hits: list[Hit] = field(default_factory=list)

    @property
    def level(self) -> str:
        """``"none"``, ``"mild"`` or ``"severe"`` (the worst hit)."""
        if not self.hits:
            return "none"
        return "severe" if any(h.severity == "nang" for h in self.hits) else "mild"

    @property
    def categories(self) -> list[str]:
        return sorted({h.category for h in self.hits})


def fold(text: str) -> str:
    """Lower case without diacritics (đ → d)."""
    text = text.lower().replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def _words(text: str, *, leet: bool) -> tuple[list[str], list[str]]:
    """``(words, runs)`` of the text. Separators between letters are removed; a run of single letters ("đ m", "d i t m e") becomes
    one word and is also returned in `runs`, because there the word boundaries were hidden on purpose."""
    text = unicodedata.normalize("NFC", text).lower()
    if leet:
        # digits stand for letters only inside a word that also has letters ("d1t"), never in a plain number
        text = re.sub(r"(?<=[^\W\d_])[\d@$!]+|[\d@$!]+(?=[^\W\d_])", lambda m: m.group().translate(_LEET), text)
    text = _SEPARATORS.sub("", text)
    tokens = re.findall(r"(?:[^\W_]|\*)+", text)
    words: list[str] = []
    runs: list[str] = []
    run: list[str] = []
    for token in tokens + [""]:
        if len(token) == 1 and (token.isalpha() or token == "*"):
            run.append(token)
            continue
        if run:
            words.append("".join(run))
            if len(run) > 1:
                runs.append("".join(run))
            run = []
        if token:
            words.append(token)
    return words, runs


def _stretched(words: list[str]) -> list[list[str]]:
    """The words as typed and with every stretched run cut to two and to one letter ('địttt mẹeee' → 'địtt mẹee' / 'địt mẹe')."""
    return [words, [_STRETCH.sub(r"\1\1", w) for w in words], [_STRETCH.sub(r"\1", w) for w in words]]


@lru_cache(maxsize=1)
def _entries() -> tuple[tuple[tuple[str, ...], str, str, str, bool], ...]:
    rows = yaml.safe_load(LEXICON.read_text(encoding="utf-8"))
    out = []
    for row in rows:
        folded = bool(row.get("f"))
        words = tuple(_words(fold(row["t"]) if folded else row["t"], leet=False)[0])
        out.append((words, row["t"], row["c"], row["s"], folded))
    return tuple(out)


def _same(word: str, needle: str) -> bool:
    """Equal, or equal where a '*' in the typed word stands for one letter."""
    if word == needle:
        return True
    return "*" in word and len(word) == len(needle) and all(w in ("*", n) for w, n in zip(word, needle))


def _find(words: list[str], needle: tuple[str, ...]) -> list[int]:
    n = len(needle)
    return [i for i in range(len(words) - n + 1) if all(_same(words[i + k], needle[k]) for k in range(n))]


def check(text: str) -> Verdict:
    """What in `text` the lexicon objects to (an empty verdict for an ordinary message)."""
    exact, exact_runs = _words(text, leet=True)
    plain, plain_runs = _words(fold(text), leet=True)
    forms = {False: (_stretched(exact), exact_runs), True: (_stretched(plain), plain_runs)}
    verdict, seen = Verdict(), set()
    for words, term, category, severity, folded in _entries():
        candidates, runs = forms[folded]
        glued = "".join(words)
        at = next((i for form in candidates for i in _find(form, words)[:1]), None)
        if at is None and len(glued) >= 3 and any(glued in run for run in runs):  # "d i t m e"
            at = 0
        if at is None or term in seen:
            continue
        seen.add(term)
        context = " ".join(candidates[0][max(0, at - 6):at + len(words) + 6])
        verdict.hits.append(Hit(term, category, severity, context[:2 * EXCERPT + len(term)]))
    return verdict
