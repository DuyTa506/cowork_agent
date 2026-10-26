"""Spelling check of one file or pasted text ("Kiểm tra chính tả"), independent of the document store.

* `engine`   — doccheck's spelling layers as the screen shows them: findings, ignore list, corrections, report
* `sessions` — the user's temporary file or text, results and lifetime (the format-check session machinery, `purpose="spell"`)
"""
from . import engine, sessions

__all__ = ["engine", "sessions"]
