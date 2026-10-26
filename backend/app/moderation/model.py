"""The classifier layer of the input screening: ViSoBERT fine-tuned on ViHSD (CLEAN / OFFENSIVE / HATE), run on CPU with ONNX Runtime.

About 6 ms for a short message on one core. The files come from `tools/export_moderation_model.py` and live in
`config.MODERATION_MODEL_DIR`; when they are missing `available()` is false and the screening uses the word rules alone.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.core import config

log = logging.getLogger(__name__)

LABELS = ("CLEAN", "OFFENSIVE", "HATE")
MAX_TOKENS = 256
WINDOW = 200  # a longer message is cut into pieces of this many tokens and the worst piece counts
THREADS = 2


@dataclass(frozen=True)
class Scores:
    clean: float
    offensive: float
    hate: float

    @property
    def label(self) -> str:
        return LABELS[int(np.argmax((self.clean, self.offensive, self.hate)))]

    @property
    def toxic(self) -> float:
        """Probability that the text is not clean."""
        return 1.0 - self.clean


class HateModel:
    """Loads the ONNX file and the sentencepiece model once; `scores` is safe to call from several threads."""

    def __init__(self, folder: Path):
        import onnxruntime as ort
        import sentencepiece as spm

        options = ort.SessionOptions()
        options.intra_op_num_threads = THREADS
        self._session = ort.InferenceSession(str(folder / "model.int8.onnx"), options, providers=["CPUExecutionProvider"])
        self._sp = spm.SentencePieceProcessor(model_file=str(folder / "sentencepiece.bpe.model"))

    def _ids(self, text: str) -> list[list[int]]:
        # XLM-R numbering: <s>=0 <pad>=1 </s>=2 <unk>=3; sentencepiece ids from 3 up are shifted by one.
        pieces = [i + 1 if i > 2 else 3 for i in self._sp.encode(text)] or [3]
        return [[0] + pieces[i:i + WINDOW] + [2] for i in range(0, len(pieces), WINDOW)]

    def scores(self, texts: list[str]) -> list[Scores]:
        windows = [(n, ids) for n, text in enumerate(texts) for ids in self._ids(text)]
        if not windows:
            return []
        width = max(len(ids) for _, ids in windows)
        ids = np.array([w + [1] * (width - len(w)) for _, w in windows], dtype=np.int64)
        mask = np.array([[1] * len(w) + [0] * (width - len(w)) for _, w in windows], dtype=np.int64)
        logits = self._session.run(None, {"input_ids": ids, "attention_mask": mask})[0]
        probs = np.exp(logits - logits.max(-1, keepdims=True))
        probs /= probs.sum(-1, keepdims=True)
        worst: dict[int, np.ndarray] = {}
        for (n, _), p in zip(windows, probs):
            if n not in worst or p[0] < worst[n][0]:
                worst[n] = p
        return [Scores(*map(float, worst[n])) for n in range(len(texts))]


_lock = threading.Lock()
_model: HateModel | None = None
_tried = False


def get() -> HateModel | None:
    """The shared model, loaded on first use; ``None`` when its files are not there or do not load."""
    global _model, _tried
    if _tried:
        return _model
    with _lock:
        if not _tried:
            folder = config.MODERATION_MODEL_DIR
            try:
                if (folder / "model.int8.onnx").is_file() and (folder / "sentencepiece.bpe.model").is_file():
                    _model = HateModel(folder)
                    log.info("moderation: classifier loaded from %s", folder)
                else:
                    log.warning("moderation: no classifier in %s, the word rules run alone", folder)
            except Exception:  # noqa: BLE001  (a broken file must not take the chat down)
                log.exception("moderation: the classifier in %s could not be loaded", folder)
            _tried = True
    return _model


def available() -> bool:
    return get() is not None
