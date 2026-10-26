"""Schema upkeep without a migration framework.

The schema is small and a deployment has a single database, so a full migration tool would be more machinery than value yet.
`ensure_schema` builds missing tables and adds columns that a newer model gained to tables that already exist, so upgrading the
code does not require touching the database by hand. It never drops, renames or retypes anything: those changes are deliberate
manual steps (and the moment to adopt Alembic).
"""
from __future__ import annotations

import logging

from sqlalchemy import JSON, Boolean, Column, Integer, inspect, text
from sqlalchemy.engine import Engine

from app import models  # noqa: F401  (importing registers every table on Base.metadata)

from .database import Base

log = logging.getLogger(__name__)


def _default_literal(column: Column) -> str:
    """SQL default for a NOT NULL column added to a table that already holds rows (existing rows need *some* value)."""
    arg = getattr(column.default, "arg", None)
    if isinstance(column.type, JSON):
        return "'[]'" if arg is list else "'{}'"
    if isinstance(column.type, Boolean):
        return "TRUE" if arg is True else "FALSE"
    if isinstance(column.type, Integer):
        return str(arg) if isinstance(arg, int) and not isinstance(arg, bool) else "0"
    if isinstance(arg, str):
        return "'" + arg.replace("'", "''") + "'"
    return "''"


def add_missing_columns(engine: Engine) -> list[str]:
    """Adds model columns absent from existing tables and returns their `table.column` names."""
    added: list[str] = []
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            present = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in present or column.primary_key:
                    continue
                ddl = f'"{column.name}" {column.type.compile(dialect=engine.dialect)}'
                if not column.nullable:
                    ddl += f" NOT NULL DEFAULT {_default_literal(column)}"
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN {ddl}'))
                added.append(f"{table.name}.{column.name}")
    if added:
        log.info("Added columns: %s", ", ".join(added))
    return added


def ensure_schema(engine: Engine) -> list[str]:
    """Creates missing tables, then adds missing columns. Safe to run on every start; returns the columns it added."""
    Base.metadata.create_all(bind=engine)
    return add_missing_columns(engine)
