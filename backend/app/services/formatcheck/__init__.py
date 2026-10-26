"""Format and spelling check of a single file ("Kiểm tra thể thức"), independent of the document store.

* `engine`   — adapter around doccheck (check, plan, apply selected edits, reports)
* `sessions` — the user's temporary file, results, lifetime and the explicit "save to store"
"""
from . import engine, sessions

__all__ = ["engine", "sessions"]
