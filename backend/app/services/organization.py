"""The organisation chart and what each user may see in it (thin wrapper over `app.org`)."""
from __future__ import annotations

from functools import lru_cache

from app.core.errors import ValidationFailed
from app.models import User
from app.org import Principal, Scope, UnitTree, scope_for


@lru_cache(maxsize=1)
def tree() -> UnitTree:
    """The unit tree, loaded once per process from ``app/org/units.yaml``."""
    return UnitTree.load()


def principal_of(user: User) -> Principal:
    """The user as the access layer sees them: unit and role only."""
    return Principal(user.unit_id, user.role)


def scope_of(user: User) -> Scope:
    """Documents the user may read. An unknown or empty unit yields an empty scope (access fails closed)."""
    if user.unit_id not in tree().units:
        return Scope(user.unit_id, frozenset(), frozenset())
    return scope_for(tree(), principal_of(user))


def require_unit(unit_id: str) -> None:
    """Raises `ValidationFailed` unless `unit_id` exists in the chart."""
    if unit_id not in tree().units:
        raise ValidationFailed(f"Đơn vị '{unit_id}' không có trong sơ đồ tổ chức.")


def units_for_display() -> list[dict]:
    """Flat list for dropdowns: id, name, type, parent and depth, in chart order."""
    chart = tree()
    out: list[dict] = []

    def walk(unit_id: str, depth: int) -> None:
        unit = chart.get(unit_id)
        out.append({"id": unit.id, "name": unit.name, "type": unit.type, "parent": unit.parent, "depth": depth,
                    "provisional": unit.provisional})
        for child in chart.children(unit_id):
            walk(child, depth + 1)

    for root in chart.children(""):
        walk(root, 0)
    return out
