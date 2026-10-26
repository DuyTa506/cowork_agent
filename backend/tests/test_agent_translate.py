"""Turning the harness's events into chat steps, and numbering citations."""
import json
import unittest

from app.agent.citations import SourceRegistry, json_values, number_citations
from app.agent.translate import Translator


def hit(doc_id, chunk, section="I. MỤC ĐÍCH", text="nội dung", pi=(3, 4)):
    return {"cite": f"{doc_id}#{chunk}", "doc_id": doc_id, "doc": "KH 21/KH-CB", "section": section, "text": text, "pi": list(pi)}


class CitationTest(unittest.TestCase):
    def setUp(self):
        self.registry = SourceRegistry()
        self.registry.add_results([hit("12", 3), hit("12", 4), hit("7", 1, "II. KINH PHÍ")])

    def test_codes_are_renumbered_in_order_of_first_use(self):
        text, cites = number_citations("A [7#1] rồi B [12#3] và C [12#4].", self.registry)
        self.assertEqual(text, "A [1] rồi B [2] và C [2].")  # 12#3 and 12#4 are the same document and section
        self.assertEqual([(c["n"], c["doc_id"]) for c in cites], [(1, "7"), (2, "12")])

    def test_unknown_codes_vanish_and_ordinary_brackets_stay(self):
        text, cites = number_citations("Xem [99#1] và phụ lục [A] theo [12#3, 7#1].", self.registry)
        self.assertEqual(text, "Xem  và phụ lục [A] theo [1][2].")
        self.assertEqual(len(cites), 2)

    def test_concatenated_json_results_are_all_read(self):
        values = json_values('{"cite": "1#1"}\n{"cite": "1#2"},[{"cite": "2#1"}]')
        self.assertEqual([v["cite"] for v in values], ["1#1", "1#2", "2#1"])


def event(kind, at, **data):
    return {"type": kind, "time": at, "data": data}


class TranslatorTest(unittest.TestCase):
    def run_turn(self, results_text, failed=False):
        tr = Translator()
        out = []
        out += tr.feed(event("step/start", 1000))
        out += tr.feed(event("assistant/message", 3000, message={"content": [
            {"type": "reasoning", "text": "Cần tìm kế hoạch. Sau đó trả lời."},
            {"type": "tool-call", "id": "c1"}]}))
        out += tr.feed(event("tool/call", 3100, name="mcp__qk3__search_documents", callId="c1",
                             arguments=json.dumps({"query": "tập huấn", "mode": "keyword"})))
        out += tr.feed(event("tool/call", 3100, name="mcp__qk3__read_document", callId="c2", arguments=json.dumps({"doc_id": "12"})))
        out += tr.feed(event("tool/result", 3500, message={"toolCallId": "c1", "isError": failed, "content": [{"type": "text", "text": results_text}]}))
        out += tr.feed(event("assistant/message", 4000, message={"content": [{"type": "text", "text": "Có [12#3]."}]}))
        out += tr.feed(event("turn/end", 4100, reason={"kind": "completed"}))
        return tr, out

    def test_parallel_calls_become_running_rows_that_finish_on_their_result(self):
        tr, out = self.run_turn(json.dumps([hit("12", 3), hit("12", 4)]))
        rows = [e["step"] for e in out if e["type"] == "step"]
        thinking = rows[0]
        self.assertEqual((thinking["kind"], thinking["title"]), ("thinking", "Đã suy nghĩ 2 giây"))
        self.assertEqual(thinking["summary"], "Cần tìm kế hoạch.")
        self.assertEqual([r["status"] for r in rows[1:3]], ["running", "running"])  # both calls appear before any result
        done = rows[3]
        self.assertEqual((done["id"], done["status"]), (rows[1]["id"], "done"))
        self.assertIn("2 đoạn trong 1 văn bản", done["summary"])
        self.assertIn("0,4 giây", done["summary"])
        text, cites = tr.finish()
        self.assertEqual((text, cites[0]["doc_id"]), ("Có [1].", "12"))

    def test_tool_errors_show_on_the_row(self):
        tr, out = self.run_turn("lỗi kết nối", failed=True)
        row = [e["step"] for e in out if e["type"] == "step"][-1]
        self.assertEqual((row["status"], row["detail"]["result"]), ("error", {"error": "lỗi kết nối"}))

    def test_failed_turn_without_answer_is_reported(self):
        tr = Translator()
        tr.feed(event("turn/end", 1, reason={"kind": "error", "message": "model unreachable"}))
        self.assertEqual((tr.answer, tr.failure), ("", "model unreachable"))


if __name__ == "__main__":
    unittest.main()
