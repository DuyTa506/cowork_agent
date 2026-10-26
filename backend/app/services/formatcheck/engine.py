"""Adapter around `doccheck`: the only module that touches its API.

doccheck checks a document against a rule profile (Thông tư 68, Nghị định 30...), lists the edits it could make with stable ids,
and applies just the chosen ones as Word tracked changes. Its own web UI ships helpers that turn a result into display data
(`doccheck.ui.analysis`) and select edits (`doccheck.ui.select`); they are reused here so this screen behaves like doccheck's. They
are not a documented public API, so everything that depends on them is kept in this file and covered by the tests.
"""
from __future__ import annotations

import glob
import os
import shutil
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import doccheck
from doccheck import errmsg, report
from doccheck.convert import ConvertError, to_docx
from doccheck.ui import analysis
from doccheck.ui.select import ENGINE

from app.core.errors import ValidationFailed
from app.services import settings

MAX_ZIP_ENTRIES = 5000
MAX_UNPACKED = 256 * 1024 * 1024  # a .docx that unpacks to more than this is treated as a zip bomb
KIND_LABEL = {"word": "Word", "pdf": "PDF"}
PDF_NOTE = "PDF không sửa trực tiếp được: sửa ở tệp gốc rồi xuất lại PDF."
# findings that say "no seal/signature/number in the file": wrong for a PDF whose stamps are form fields or pictures laid on afterwards
STAMPED_RULES = {"MX.M06.8_dau_chu_ky_so.presence", "QC.D10.1g.chu_ky_so_nguoi_ky.presence", "INFO.so_chua_cap"}

_rule_bases: dict[str, Any] = {}
_lock = threading.Lock()


@dataclass
class Analysis:
    """Outcome of one check: the display payload and the two headline numbers."""

    payload: dict[str, Any]
    counts: dict[str, int]


def profiles() -> list[dict[str, Any]]:
    """Rule profiles the screen offers: ``[{"id", "label", "experimental"}]``."""
    return [{"id": p.name, "label": p.label, "experimental": p.experimental} for p in doccheck.profiles()]


def rule_base(profile: str) -> Any:
    """The rule base of `profile`, built once per process.

    Raises:
        ValidationFailed: unknown profile.
    """
    if profile not in {p["id"] for p in profiles()}:
        raise ValidationFailed(f"Bộ luật '{profile}' không có.")
    with _lock:
        if profile not in _rule_bases:
            _rule_bases[profile] = doccheck.RuleBase(profile)
        return _rule_bases[profile]


def prepare(upload: Path, extension: str, directory: Path) -> tuple[Path, str]:
    """Puts the uploaded file in `directory` in a form doccheck can check and returns ``(path, kind)``.

    ``.docx`` is validated as is; a legacy ``.doc`` is converted to ``.docx`` (natively, no Office needed); ``.pdf`` is checked
    for a text layer. ``kind`` is ``"word"`` (can be checked and fixed) or ``"pdf"`` (checked only).

    Raises:
        ValidationFailed: not a readable Word/PDF file, or a scan without a text layer.
    """
    if extension == ".pdf":
        target = directory / "source.pdf"
        shutil.move(upload, target)
        if _is_scan(target):
            raise ValidationFailed("Đây là bản scan (PDF không có lớp chữ), chưa kiểm tra được.")
        return target, "pdf"
    target = directory / "source.docx"
    if extension == ".docx":
        shutil.move(upload, target)
    else:
        try:
            shutil.copyfile(to_docx(str(upload)), target)
        except ConvertError as exc:
            raise ValidationFailed(f"Không đọc được tệp: {exc}") from exc
        upload.unlink(missing_ok=True)
    _validate_docx(target)
    return target, "word"


def _is_scan(path: Path) -> bool:
    """True for a PDF with no text layer, or whose text is OCR output (nothing reliable to check)."""
    try:
        return bool(doccheck.pdf_is_ocr(str(path))[0])
    except Exception:  # noqa: BLE001  (an unreadable PDF is reported by the check itself)
        return False


def _validate_docx(path: Path) -> None:
    """Rejects files that are not a Word package or that unpack suspiciously large."""
    if not zipfile.is_zipfile(path):
        raise ValidationFailed("Tệp không phải .docx hợp lệ.")
    with zipfile.ZipFile(path) as package:
        entries = package.infolist()
        if len(entries) > MAX_ZIP_ENTRIES or sum(e.file_size for e in entries) > MAX_UNPACKED:
            raise ValidationFailed("Tệp .docx quá lớn hoặc có cấu trúc bất thường.")
        if "word/document.xml" not in package.namelist():
            raise ValidationFailed("Tệp không phải văn bản Word (.docx).")


def _ensure_ort() -> None:
    """Points doccheck at the ONNX Runtime library of the installed `onnxruntime` package when it has none of its own (its deep spelling
    model needs that library; the version doccheck pins, 1.31, is the one requirements.txt installs)."""
    if os.environ.get("DOCCHECK_ORT_LIB") or doccheck.gec_info()["onnxruntime"]:
        return
    try:
        import onnxruntime
    except ImportError:
        return
    found = sorted(glob.glob(os.path.join(os.path.dirname(onnxruntime.__file__), "capi", "libonnxruntime.so*")))
    if found:
        os.environ["DOCCHECK_ORT_LIB"] = found[-1]


def deep_options() -> dict[str, Any]:
    """The administrator's choice for the deep spelling model as keyword arguments of `doccheck.check` / `spell_text`
    (``spell_deep``: off | auto | default | fast)."""
    try:
        values = settings.cache.get("doccheck")
    except Exception:  # noqa: BLE001  (no database to read: the defaults)
        values = {}
    mode = values.get("spell_deep", "default")
    if mode == "off":
        return {}
    _ensure_ort()
    return {"deep": mode, "gate": values.get("spell_deep_gate", "off"), "deep_low": bool(values.get("spell_deep_low"))}


def run_check(source: Path, profile: str, spell: bool) -> Any:
    """Runs doccheck on `source`, with the offline spelling layers when `spell` is on: dictionary and rules, the n-gram language model
    and, if the administrator allows and the machine has it, the deep model."""
    options = {"spell": {"tone_style": "majority"}, "lm": "auto", **deep_options()} if spell else {}
    try:
        return doccheck.check(str(source), rule_base(profile), None, with_model=True, **options)
    except doccheck.ScannedPDF as exc:
        raise ValidationFailed("Đây là bản scan (PDF không có lớp chữ), chưa kiểm tra được.") from exc
    except ValidationFailed:
        raise
    except Exception as exc:  # noqa: BLE001  (doccheck raises plain OSError/ValueError with Vietnamese messages)
        raise ValidationFailed(errmsg.vi_error(exc, str(source))) from exc


def analyze(source: Path, kind: str, profile: str, spell: bool, name: str, session_id: str) -> Analysis:
    """Checks `source` and returns what the screen shows: facts, findings per paragraph, selectable fixes, manual notes."""
    rb = rule_base(profile)
    result = run_check(source, profile, spell)
    stamp_note = _drop_false_absences(source, result) if kind == "pdf" else ""
    plan = analysis.pdf_plan(result) if kind == "pdf" else ENGINE.plan(str(source), str(source.parent), result, rb)
    payload = analysis.build(session_id, name, result, plan, bool(spell), "majority")
    payload.update(kind=kind, kind_label=KIND_LABEL[kind], can_fix=kind == "word", note=(PDF_NOTE + " " + stamp_note).strip() if kind == "pdf" else "",
                   profile={"id": rb.name, "label": rb.label, "experimental": bool(rb.profile["experimental"])})
    return Analysis(payload, {"format": payload["counts"]["format"], "spelling": payload["counts"]["spelling"]})


def _drop_false_absences(source: Path, result: Any) -> str:
    """For a PDF with stamps (seal, digital signature, number and date fields filled in by another system) removes the findings that claim
    the number, signature or seal is missing, and returns a note saying what is there (read by OCR when it is on)."""
    from app import ocr
    from app.ocr.render import stamp_pages
    from app.parsing import ParseError, parse_file

    if not stamp_pages(source):
        return ""
    result.findings = [f for f in result.findings if f.rule_id not in STAMPED_RULES]
    detail = ""
    try:
        parsed = parse_file(source)
        found = ocr.read_stamps_file(source, parsed)
        meta = parsed.metadata
        parts = [f"số {meta.number}/{meta.symbol}" if meta.number else "", f"ngày {meta.date[8:]}/{meta.date[5:7]}/{meta.date[:4]}" if meta.date else "",
                 f"người ký {meta.signer}" if meta.signer and meta.signer_name else ""]
        detail = (" Đọc từ ảnh bằng OCR: " + "; ".join(p for p in parts if p) + ".") if found else ""
    except (ParseError, ValidationFailed):
        pass
    return "Tệp có dấu / chữ ký số được chèn từ hệ thống khác (số, ngày, người ký không nằm trong lớp chữ) nên các mục này không kiểm tra từ lớp chữ." + detail


def apply(source: Path, profile: str, spell: bool, ids: list[str], mode: str, out: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Writes `out` (.docx) with only the edits `ids`. Returns ``(applied ids, [{"id", "reason"}])`` for the ones that failed.

    The check and the plan are recomputed: their ids depend only on the file, the rules and the options, so they match what the
    screen showed without any state kept between requests.

    Raises:
        ValidationFailed: unknown id or bad mode.
    """
    if mode not in ("track", "apply"):
        raise ValidationFailed("Chế độ sửa phải là 'track' hoặc 'apply'.")
    rb = rule_base(profile)
    plan = ENGINE.plan(str(source), str(source.parent), run_check(source, profile, spell), rb)
    try:
        outcome = ENGINE.apply(plan, ids, mode, str(out))
    except ValueError as exc:
        raise ValidationFailed(str(exc)) from exc
    return outcome.applied, [{"id": item, "reason": reason} for item, reason in outcome.failed]


def report_text(source: Path, profile: str, spell: bool) -> str:
    """Plain-text report of every finding (for the "Tải báo cáo lỗi" button)."""
    return report.to_text(run_check(source, profile, spell))


def write_annotated(source: Path, profile: str, spell: bool, out: Path) -> None:
    """Copy of the document with each finding as a Word comment on its paragraph."""
    report.write_commented_docx(run_check(source, profile, spell), str(out))
