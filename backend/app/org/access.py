"""Who may see which document. Deliberately small: the rule is two checks, unit scope and secrecy level.

Early stage by design (no per-document ACLs): extend by adding roles to ROLE_LEVELS, levels to LEVELS, or a check in
Scope.allows(). Everything that reads documents (listing, search, RAG retrieval) must go through a Scope, and the filter
belongs in the query itself (unit_id IN scope.unit_ids AND level IN scope.levels), never applied to the results afterwards.
"""
from __future__ import annotations
from dataclasses import dataclass

from .units import UnitTree

LEVELS = ("thuong", "mat")  # ordinary | secret (mật, tối mật and tuyệt mật are all "mat" for access purposes)
# Levels each role may read. Commanders see secret documents; admin manages the system and, by least privilege, does not.
ROLE_LEVELS: dict[str, frozenset[str]] = {
    "commander": frozenset({"thuong", "mat"}),
    "admin": frozenset({"thuong"}),
    "reviewer": frozenset({"thuong"}),
    "staff": frozenset({"thuong"}),
}
ROOT_UNIT = "btl"  # a document whose unit is unknown is attached to the top, so only the root (Quân khu 3) scope reaches it

@dataclass(frozen=True)
class Principal:
    unit_id: str
    role: str

@dataclass(frozen=True)
class Scope:
    unit_id: str  # the user's own unit: an indexed chunk is readable iff this is in its unit_path
    unit_ids: frozenset[str]  # the unit's subtree, for code that filters in Python rather than in the index
    levels: frozenset[str]

    def allows(self, unit_id: str, level: str) -> bool:
        return unit_id in self.unit_ids and level in self.levels

@dataclass(frozen=True)
class Placement:
    unit_id: str
    level: str
    unit_path: tuple[str, ...] = ()  # root-to-unit ids, indexed with every chunk (see UnitTree.path_to)
    reasons: tuple[str, ...] = ()  # why it is secret / why the unit is the root, for audit and debugging

def scope_for(tree: UnitTree, who: Principal) -> Scope:
    """The documents `who` may read: their unit's subtree, at the levels their role allows (an unknown role gets ordinary only)."""
    return Scope(who.unit_id, tree.subtree(who.unit_id), ROLE_LEVELS.get(who.role, frozenset({"thuong"})))

def place(tree: UnitTree, folder_parts: list[str], classification: str = "") -> Placement:
    """Unit and level of a document from its folder and the secrecy stamp on it; secret if either says so."""
    found = tree.resolve_path(folder_parts)
    reasons = []
    if found.secret_folder:
        reasons.append("thư mục văn bản mật")
    if classification:
        reasons.append(f"dấu độ mật trên văn bản ({classification})")
    unit = found.unit_id
    if unit is None:
        unit = ROOT_UNIT
        reasons.append("không xác định được đơn vị")
    return Placement(unit, "mat" if found.secret_folder or classification else "thuong", tree.path_to(unit), tuple(reasons))

def place_upload(tree: UnitTree, uploader: Principal, classification: str = "", declared_secret: bool = False) -> Placement:
    """Placement of a document uploaded through the app: it belongs to the uploader's unit, and is secret when the document
    carries a secrecy stamp or the uploader marks it so."""
    reasons = []
    if classification:
        reasons.append(f"dấu độ mật trên văn bản ({classification})")
    if declared_secret:
        reasons.append("người tải lên đánh dấu mật")
    return Placement(uploader.unit_id, "mat" if reasons else "thuong", tree.path_to(uploader.unit_id), tuple(reasons))
