"""Format check of a draft: render it, run doccheck on the file, summarise what a person must act on."""
from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.formatcheck import engine

from .content import DraftContent
from .render import render

PROFILE = "tt68"
# Findings the application cannot judge from a draft (signature, seal, line length): the person does these on the signed copy.
MANUAL_MARKER = "cần kiểm tay"
SEVERITIES = ("error", "warning")


def check_draft(content: DraftContent) -> dict[str, Any]:
    """Checks the draft against Thông tư 68 as the .docx would be written.

    Returns ``{"counts": {"error", "warning", "manual"}, "findings": [{"severity", "message", "where", "ref"}], "checked_at"}``;
    ``manual`` counts the points that only the signed copy can show.
    """
    with tempfile.TemporaryDirectory(prefix="draft-") as folder:
        path = render(content, Path(folder) / "du-thao.docx", for_check=True)
        result = engine.run_check(path, PROFILE, False)
    findings, manual = [], 0
    for item in result.findings:
        if MANUAL_MARKER in item.message or item.severity not in SEVERITIES:
            manual += 1
            continue
        findings.append({"severity": item.severity, "message": item.message, "where": (item.excerpt or "")[:160], "ref": item.ref})
    counts = {"error": sum(f["severity"] == "error" for f in findings), "warning": sum(f["severity"] == "warning" for f in findings),
              "manual": manual}
    return {"counts": counts, "findings": findings, "checked_at": datetime.now(timezone.utc).isoformat()}
