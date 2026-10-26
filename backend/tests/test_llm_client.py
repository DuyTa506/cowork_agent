"""The direct chat client used by server-side tools (summaries): thinking switched off, graceful fallbacks, clear errors."""
import json
import unittest

import httpx

from app.rag.llm import LlmClient, LlmError


def _client(handler) -> LlmClient:
    client = LlmClient({"base_url": "http://llm/v1", "model": "m"})
    client._client = httpx.Client(base_url="http://llm/v1", transport=httpx.MockTransport(handler))
    return client


def _reply(content, finish="stop"):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}, "finish_reason": finish}]})


class LlmClientTests(unittest.TestCase):
    def test_thinking_is_switched_off_for_direct_calls(self):
        seen = []

        def handler(request):
            seen.append(json.loads(request.content))
            return _reply("  Tóm tắt.  ")

        self.assertEqual(_client(handler).complete("s", "u"), "Tóm tắt.")
        self.assertEqual(seen[0]["chat_template_kwargs"], {"enable_thinking": False})

    def test_a_strict_server_that_rejects_the_option_gets_a_plain_request(self):
        bodies = []

        def handler(request):
            body = json.loads(request.content)
            bodies.append(body)
            return httpx.Response(400, json={"error": "unknown field"}) if "chat_template_kwargs" in body else _reply("ok")

        self.assertEqual(_client(handler).complete("s", "u"), "ok")
        self.assertEqual(len(bodies), 2)
        self.assertNotIn("chat_template_kwargs", bodies[1])

    def test_an_answer_cut_off_inside_the_reasoning_says_so(self):
        with self.assertRaisesRegex(LlmError, "suy luận"):
            _client(lambda request: _reply("", "length")).complete("s", "u")

    def test_an_empty_answer_and_a_server_error_are_reported(self):
        with self.assertRaisesRegex(LlmError, "rỗng"):
            _client(lambda request: _reply("")).complete("s", "u")
        with self.assertRaises(LlmError):
            _client(lambda request: httpx.Response(500)).complete("s", "u")


if __name__ == "__main__":
    unittest.main()
