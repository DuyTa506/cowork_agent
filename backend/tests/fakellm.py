"""A scripted, OpenAI-compatible chat server for tests and offline demos: no model, deterministic answers.

`FakeLLM(script)` listens on a free local port. For every `/v1/chat/completions` request it calls ``script(messages, tools)`` and
streams back what it returns: ``{"reasoning": str, "content": str, "tool_calls": [{"name": str, "arguments": dict}]}`` (all keys
optional). It supports ``stream: true`` (server-sent events, text in small pieces so streaming can be observed) and plain JSON.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

Script = Callable[[list[dict[str, Any]], list[dict[str, Any]]], dict[str, Any]]


class FakeLLM:
    """Context manager: ``with FakeLLM(script) as llm: llm.base_url``. `requests` keeps every request body received."""

    def __init__(self, script: Script, piece_chars: int = 12, delay: float = 0.0, reasoning_field: str = "reasoning_content"):
        self.script, self.piece_chars, self.delay = script, piece_chars, delay
        self.reasoning_field = reasoning_field  # vLLM calls it "reasoning", SGLang and llama.cpp "reasoning_content"
        self.requests: list[dict[str, Any]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # keep test output clean
                pass

            def do_GET(self):  # noqa: N802
                self._json({"object": "list", "data": [{"id": "fake-model", "object": "model"}]})

            def do_POST(self):  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"{}")
                outer.requests.append(body)
                action = outer.script(body.get("messages", []), body.get("tools", []))
                (self._stream if body.get("stream") else self._complete)(body, action)

            def _json(self, obj: dict[str, Any]) -> None:
                data = json.dumps(obj, ensure_ascii=False).encode()
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _complete(self, body: dict, action: dict) -> None:
                message: dict[str, Any] = {"role": "assistant", "content": action.get("content", "")}
                calls = outer._calls(action)
                if calls:
                    message["tool_calls"] = calls
                self._json({"id": "cmpl-" + uuid.uuid4().hex[:8], "object": "chat.completion", "model": body.get("model", "fake"),
                            "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if calls else "stop"}],
                            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}})

            def _stream(self, body: dict, action: dict) -> None:
                self.send_response(200)
                self.send_header("content-type", "text/event-stream")
                self.send_header("cache-control", "no-cache")
                self.end_headers()
                ident, model = "cmpl-" + uuid.uuid4().hex[:8], body.get("model", "fake")

                def send(delta: dict, finish: str | None = None, usage: dict | None = None) -> None:
                    chunk = {"id": ident, "object": "chat.completion.chunk", "model": model,
                             "choices": [{"index": 0, "delta": delta, "finish_reason": finish}] if delta or finish else []}
                    if usage:
                        chunk["usage"] = usage
                    self.wfile.write(b"data: " + json.dumps(chunk, ensure_ascii=False).encode() + b"\n\n")
                    self.wfile.flush()
                    if outer.delay:
                        time.sleep(outer.delay)

                send({"role": "assistant", "content": ""})
                for piece in outer._pieces(action.get("reasoning", "")):
                    send({outer.reasoning_field: piece})
                for piece in outer._pieces(action.get("content", "")):
                    send({"content": piece})
                calls = outer._calls(action)
                for i, call in enumerate(calls):
                    send({"tool_calls": [{"index": i, "id": call["id"], "type": "function",
                                          "function": {"name": call["function"]["name"], "arguments": ""}}]})
                    send({"tool_calls": [{"index": i, "function": {"arguments": call["function"]["arguments"]}}]})
                send({}, "tool_calls" if calls else "stop")
                send({}, usage={"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20})
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def _pieces(self, text: str) -> list[str]:
        """Splits text into small pieces, as a model streams it."""
        return [text[i:i + self.piece_chars] for i in range(0, len(text), self.piece_chars)]

    @staticmethod
    def _calls(action: dict[str, Any]) -> list[dict[str, Any]]:
        """Tool calls of an action in the OpenAI wire shape."""
        return [{"id": "call_" + uuid.uuid4().hex[:12], "type": "function",
                 "function": {"name": c["name"], "arguments": json.dumps(c.get("arguments", {}), ensure_ascii=False)}}
                for c in action.get("tool_calls", [])]

    @property
    def base_url(self) -> str:
        """Base URL to give the application as the LLM endpoint."""
        return f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    def __enter__(self) -> "FakeLLM":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._server.shutdown()
        self._server.server_close()
