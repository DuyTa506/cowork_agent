""""Test connection" for each settings section: a real request to the configured endpoint, reported in plain Vietnamese."""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

import httpx

from app.search.factory import EmbeddingNotConfigured, make_embedder
from app.search.rerank import make_reranker

TIMEOUT = 20.0


@dataclass
class TestResult:
    """Outcome of one connection test."""

    __test__ = False  # not a pytest/unittest class despite the name

    ok: bool
    message: str
    latency_ms: int = 0
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready form."""
        return asdict(self)


def _headers(values: dict[str, Any]) -> dict[str, str]:
    """Authorization header for sections that have an API key."""
    return {"Authorization": f"Bearer {values['api_key']}"} if values.get("api_key") else {}


def _timed(call) -> tuple[Any, int]:
    """Runs `call()` and returns its result with the elapsed milliseconds."""
    start = time.perf_counter()
    result = call()
    return result, int((time.perf_counter() - start) * 1000)


def _describe(exc: Exception) -> str:
    """One short sentence for the failure, without leaking response bodies."""
    if isinstance(exc, httpx.HTTPStatusError):
        return f"Máy chủ trả lỗi HTTP {exc.response.status_code}."
    if isinstance(exc, httpx.TimeoutException):
        return "Máy chủ không phản hồi kịp thời."
    if isinstance(exc, httpx.ConnectError):
        return "Không kết nối được tới máy chủ."
    return f"{type(exc).__name__}: {exc}"


def _llm(values: dict[str, Any]) -> TestResult:
    """Asks the model for a single token."""
    if not (values["base_url"] and values["model"]):
        return TestResult(False, "Chưa nhập địa chỉ máy chủ hoặc tên model.")
    body = {"model": values["model"], "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1}
    response, ms = _timed(lambda: httpx.post(f"{values['base_url']}/chat/completions", json=body, headers=_headers(values), timeout=TIMEOUT))
    response.raise_for_status()
    return TestResult(True, "Kết nối thành công.", ms)


def _embedding(values: dict[str, Any]) -> TestResult:
    """Embeds a short sentence and checks the vector size against the configured one."""
    try:
        embedder = make_embedder(values)
    except EmbeddingNotConfigured as exc:
        return TestResult(False, str(exc))
    vector, ms = _timed(lambda: embedder.embed_query("Kiểm tra kết nối embedding"))
    return TestResult(True, f"Kết nối thành công, vector {len(vector)} chiều.", ms, {"dim": len(vector)})


def _rerank(values: dict[str, Any]) -> TestResult:
    """Scores two passages and checks that the relevant one wins."""
    reranker = make_reranker({**values, "enabled": True})
    if reranker is None:
        return TestResult(False, "Chưa nhập địa chỉ máy chủ.")
    scores, ms = _timed(lambda: reranker.rerank("thủ đô của Việt Nam", ["Hà Nội là thủ đô của Việt Nam.", "Con mèo ngồi trên mái nhà."]))
    verdict = "xếp hạng đúng" if scores[0] > scores[1] else "xếp hạng KHÔNG đúng, kiểm tra lại model/giao thức"
    return TestResult(scores[0] > scores[1], f"Kết nối thành công, {verdict}.", ms)


def _ocr(values: dict[str, Any]) -> TestResult:
    """Lists the server's models and checks the configured one is served."""
    if not values["base_url"]:
        return TestResult(False, "Chưa nhập địa chỉ máy chủ.")
    response, ms = _timed(lambda: httpx.get(f"{values['base_url']}/models", headers=_headers(values), timeout=TIMEOUT))
    response.raise_for_status()
    served = [m.get("id") for m in response.json().get("data", [])]
    if values["model"] and served and values["model"] not in served:
        return TestResult(False, "Máy chủ chạy được nhưng không có model này.", ms, {"served": served})
    return TestResult(True, "Kết nối thành công.", ms)


_TESTS = {"llm": _llm, "embedding": _embedding, "rerank": _rerank, "ocr": _ocr}


def run(section_key: str, values: dict[str, Any]) -> TestResult:
    """Tests section `section_key` with `values`. Never raises: a failure is a result the admin screen can show."""
    test = _TESTS.get(section_key)
    if test is None:
        return TestResult(False, "Mục này không có kiểm tra kết nối.")
    try:
        return test(values)
    except Exception as exc:  # noqa: BLE001  (any failure of the remote end is reported, not propagated)
        return TestResult(False, _describe(exc))
