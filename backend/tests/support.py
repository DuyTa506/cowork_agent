"""Helpers shared by the tests."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401  (registers the tables)
from app.core.database import Base


def memory_engine() -> Engine:
    """A fresh in-memory SQLite database with the full schema, independent of the application's configured database."""
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return engine


def memory_session() -> Session:
    """One session on a fresh in-memory database."""
    return sessionmaker(bind=memory_engine(), expire_on_commit=False)()
