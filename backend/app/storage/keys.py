"""Where each kind of file lives in the object store."""
from __future__ import annotations


def document(stored_name: str) -> str:
    """The original file of a document of the store."""
    return f"documents/{stored_name}"


def attachment(session_id: str, stored_name: str) -> str:
    """A file attached to a conversation."""
    return f"chat/{session_id}/{stored_name}"


def attachments_prefix(session_id: str) -> str:
    """Every file attached to a conversation."""
    return f"chat/{session_id}/"
