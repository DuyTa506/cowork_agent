"""The harness keeps each conversation's transcript on disk (it includes passages the tools returned), so deleting a conversation
must delete that too."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from app.core import config

log = logging.getLogger(__name__)


def home() -> Path:
    """Where the harness keeps its state (``DATA_DIR/dsh``)."""
    return config.DATA_DIR / "dsh"


def remove(session_id: str) -> int:
    """Deletes the harness transcript files of a conversation; returns how many were removed."""
    root = home()
    removed = 0
    for pattern in (f"sessions/*/{session_id}*", f"storages/*/sessions/{session_id}*"):
        for path in root.glob(pattern):
            try:
                shutil.rmtree(path) if path.is_dir() else path.unlink()
                removed += 1
            except OSError:
                log.warning("could not remove %s", path)
    return removed


def exists(session_id: str) -> bool:
    """Whether the harness already holds a transcript for the conversation (so it must be resumed, not created again)."""
    return any(home().glob(f"sessions/*/{session_id}*"))
