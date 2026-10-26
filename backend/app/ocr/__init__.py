"""Reading scanned PDFs (no text layer) with an OCR model served over an OpenAI-compatible API (Peppercorn v3 on vLLM).

Each page is rendered to an image and sent alone to the model; the pages' text becomes a plain Word file that sits next to the
original in the object store (`companion_key`) and is what the parser, the viewer and the index read from then on.
"""
from .stamps import missing as missing_stamp_fields, read_stamps, read_stamps_file
from .service import OcrDisabled, OcrError, companion_key, ensure_companion, grounding_key, is_enabled, parse_with_ocr

__all__ = ["OcrDisabled", "OcrError", "companion_key", "ensure_companion", "grounding_key", "is_enabled", "parse_with_ocr", "read_stamps", "read_stamps_file", "missing_stamp_fields"]
