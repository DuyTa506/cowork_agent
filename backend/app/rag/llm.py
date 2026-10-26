"""A small client for the configured chat model, used by server-side tools (summaries) that call it directly rather than
through the agent loop."""
from __future__ import annotations

from typing import Any

import httpx


class LlmError(RuntimeError):
    """The model server did not give a usable answer."""


class LlmClient:
    """Non-streaming ``/chat/completions`` calls against an OpenAI-compatible server.

    Args:
        values: The ``llm`` settings section (base_url, model, api_key, max_output_tokens, temperature).
    """

    def __init__(self, values: dict[str, Any], timeout: float = 300.0):
        if not (values.get("base_url") and values.get("model")):
            raise LlmError("Chưa cấu hình mô hình hội thoại (Quản trị → Hệ thống → LLM).")
        self.model = values["model"]
        self.max_tokens = int(values.get("max_output_tokens") or 2048)
        self.temperature = float(values.get("temperature", 0.2))
        self._client = httpx.Client(base_url=values["base_url"], timeout=timeout,
                                    headers={"Authorization": f"Bearer {values['api_key']}"} if values.get("api_key") else {})

    def complete(self, system: str, user: str, max_tokens: int | None = None) -> str:
        """One answer to a system + user prompt.

        Raises:
            LlmError: transport failure, error status or an empty answer.
        """
        body = {"model": self.model, "temperature": self.temperature, "max_tokens": max_tokens or self.max_tokens,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                # Reasoning models (Qwen3...) would spend the whole budget thinking and leave the answer empty; a summary needs
                # no reasoning. Servers that do not know the option ignore it; a strict one answers 400 and gets a plain request.
                "chat_template_kwargs": {"enable_thinking": False}}
        try:
            response = self._client.post("/chat/completions", json=body)
            if response.status_code == 400:
                body.pop("chat_template_kwargs")
                response = self._client.post("/chat/completions", json=body)
            response.raise_for_status()
            choice = response.json()["choices"][0]
            text = (choice["message"].get("content") or "").strip()
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            raise LlmError(f"Không gọi được mô hình: {type(exc).__name__}") from exc
        if not text:
            if choice.get("finish_reason") == "length":
                raise LlmError("Mô hình dùng hết số token cho phần suy luận; tăng 'Số token trả lời tối đa' hoặc tắt chế độ suy luận.")
            raise LlmError("Mô hình trả về nội dung rỗng.")
        return text
