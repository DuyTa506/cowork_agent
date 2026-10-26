from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.parsing.textutil import fold

DEFAULT_FILE = Path(__file__).with_name("units.yaml")
# folder-name noise that is not part of a unit's name ("Phòng Quan nhu tai lieu AI", "Cung cap Tai lieu thu nghiem AI")
_NOISE = re.compile(r"\b(CUNG CAP )?TAI LIEU( THU NGHIEM)?( AI)?\b|\bAI\b")
_SECRET_FOLDER = re.compile(r"\bVAN BAN MAT\b|\bTAI LIEU MAT\b")

def key(text: str) -> str:
    """Comparison key: no diacritics, upper case, letters and digits only ('Phòng Hoá học' == 'PHÒNG HÓA HỌC')."""
    return re.sub(r"[^A-Z0-9]+", " ", fold(text)).strip()

@dataclass(frozen=True)
class Unit:
    id: str
    name: str
    type: str
    parent: str | None = None
    aliases: tuple[str, ...] = ()
    provisional: bool = False

@dataclass
class PathMatch:
    unit_id: str | None
    matched: list[str] = field(default_factory=list)  # folder names that identified a unit, outermost first
    secret_folder: bool = False  # a folder named "văn bản mật" on the way

@dataclass
class HeaderMatch:
    unit_id: str | None
    candidates: list[str] = field(default_factory=list)  # several units share the matched name (e.g. "PHÒNG CHÍNH TRỊ")

class UnitTree:
    def __init__(self, units: list[Unit]):
        self.units = {u.id: u for u in units}
        if len(self.units) != len(units):
            raise ValueError("Trùng id đơn vị.")
        self._children: dict[str, list[str]] = {}
        for u in units:
            if u.parent is not None and u.parent not in self.units:
                raise ValueError(f"Đơn vị {u.id}: không có đơn vị cha {u.parent}.")
            self._children.setdefault(u.parent or "", []).append(u.id)
        self._aliases: dict[str, list[str]] = {}
        for u in units:
            names = {key(u.name), key(re.sub(r"\(.*?\)", "", u.name))} | {key(a) for a in u.aliases}
            for k in names - {""}:
                self._aliases.setdefault(k, []).append(u.id)

    @classmethod
    def load(cls, path: str | Path = DEFAULT_FILE) -> "UnitTree":
        rows = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls([Unit(r["id"], r["name"], r["type"], r.get("parent"), tuple(r.get("aliases", ())),
                         bool(r.get("provisional", False))) for r in rows])

    def get(self, unit_id: str) -> Unit:
        return self.units[unit_id]

    def children(self, unit_id: str) -> list[str]:
        return list(self._children.get(unit_id, []))

    def ancestors(self, unit_id: str) -> list[str]:
        out: list[str] = []
        cur = self.units[unit_id].parent
        while cur is not None:
            out.append(cur)
            cur = self.units[cur].parent
        return out

    def path_to(self, unit_id: str) -> tuple[str, ...]:
        """Root-to-unit ids, e.g. ('btl', 'btm', 'btm.cong_binh'). Stored on every indexed chunk: a user may read it iff
        their unit appears in this path, which is a single indexed match instead of a list of up to ~100 unit ids."""
        return tuple(reversed(self.ancestors(unit_id))) + (unit_id,)

    def subtree(self, unit_id: str) -> frozenset[str]:
        """The unit and everything under it: the units whose documents a user of `unit_id` may see."""
        out = {unit_id}
        stack = [unit_id]
        while stack:
            for c in self._children.get(stack.pop(), []):
                out.add(c)
                stack.append(c)
        return frozenset(out)

    def can_view(self, user_unit: str, doc_unit: str) -> bool:
        return doc_unit in self.subtree(user_unit)

    def _match_child(self, parent: str, text: str) -> str | None:
        """The child of `parent` whose name/alias is the whole of `text` or its start (at a word boundary); longest alias wins."""
        k = key(text)
        best: tuple[int, str] | None = None
        for cid in self._children.get(parent, []):
            for a, ids in self._aliases.items():
                if cid in ids and (k == a or k.startswith(a + " ")):
                    if best is None or len(a) > best[0]:
                        best = (len(a), cid)
        return best[1] if best else None

    def resolve_path(self, parts: list[str]) -> PathMatch:
        """Unit for a file from the folders above it, e.g. ['Bộ Tham mưu', 'Phòng Công Binh', 'Năm 2025'] -> btm.cong_binh."""
        cur = next(iter(self._children.get("", [])))  # the root (Quân khu 3)
        res = PathMatch(None)
        for part in parts:
            k = _NOISE.sub(" ", key(part)).strip()
            if _SECRET_FOLDER.search(k):
                res.secret_folder = True
            if not k:
                continue
            child = self._match_child(cur, part if k == key(part) else k)
            if child:
                cur = child
                res.unit_id = child
                res.matched.append(part)
        return res

    def resolve_header(self, *agencies: str) -> HeaderMatch:
        """Unit named in the agency block at the top of a document ('BỘ THAM MƯU' / 'PHÒNG CÔNG BINH'); longest name wins.

        Several units may share a name ('Ban Tài chính' exists in three agencies): then unit_id is None and the
        candidates are listed, so the caller can decide from other evidence (the folder)."""
        text = " " + key(" ".join(a for a in agencies if a)) + " "
        best_len, best_ids = 0, []
        for a, ids in self._aliases.items():
            if f" {a} " in text and len(a) > best_len:
                best_len, best_ids = len(a), ids
        if len(best_ids) == 1:
            return HeaderMatch(best_ids[0])
        return HeaderMatch(None, list(best_ids))
