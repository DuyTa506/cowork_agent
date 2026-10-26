"""The assistant end to end: HTTP -> agent harness -> MCP tools -> database/index, with a scripted model instead of a real one.

The harness (Node) and the tool process are the real ones; only the language model is `FakeLLM`. The database is a file because
the tool process is a separate program that reads and writes it.
"""
import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

from qdrant_client import QdrantClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agent.citations import json_values
from app.agent.runtime import AgentPool
from app.core import config
from app.core.database import Base
from app.models import ChatAttachment, ChatMessage, ChatSession, Draft
from app.search import HashEmbedder, QdrantIndex
from app.services import attachments, indexing, settings

import test_documents_api as base
from fakellm import FakeLLM

DIM = 64
ATT_COLLECTION = base.COLLECTION + "_att"
ATT_INDEX = QdrantIndex(QdrantClient(url=base.URL, api_key=base.KEY), HashEmbedder(DIM), ATT_COLLECTION)


def setUpModule():
    base.setUpModule()
    ATT_INDEX.ensure_collection()


def tearDownModule():
    base.tearDownModule()
    ATT_INDEX.client.delete_collection(ATT_COLLECTION)


def tool_results(messages: list[dict]) -> list[dict]:
    """Values returned by the tools in the current model step (the messages after the last assistant message)."""
    start = max((i for i, m in enumerate(messages) if m["role"] == "assistant"), default=-1)
    out: list[dict] = []
    for message in messages[start + 1:]:
        if message["role"] == "tool":
            content = message["content"]
            text = content if isinstance(content, str) else "".join(p.get("text", "") for p in content)
            out.extend(json_values(text))
    return out


def turn_step(messages: list[dict]) -> int:
    """How many model steps of the current turn came before this request."""
    last_user = max(i for i, m in enumerate(messages) if m["role"] == "user")
    return sum(1 for m in messages[last_user:] if m["role"] == "assistant")


class ChatTestCase(base.ApiTestCase):
    script = staticmethod(lambda messages, tools: {"content": "Xin chào."})

    def setUp(self):
        db_dir = Path(tempfile.mkdtemp(prefix="qk3-chat-db-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(db_dir, ignore_errors=True))
        self.db_url = f"sqlite:///{db_dir / 'test.db'}"

        def file_engine():
            engine = create_engine(self.db_url, connect_args={"check_same_thread": False})
            Base.metadata.create_all(engine)
            return engine

        with mock.patch("test_documents_api.memory_engine", file_engine):
            super().setUp()
        self.data_dir = self.tmp / "data"
        self.data_dir.mkdir()
        for patcher in (
            mock.patch.object(config, "DATA_DIR", self.data_dir),
            mock.patch.object(indexing, "attachments", lambda values=None: ATT_INDEX),
            mock.patch.object(indexing, "attachments_store_only", lambda values=None: ATT_INDEX),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        ATT_INDEX.client.delete(ATT_COLLECTION, points_selector=__import__("qdrant_client").models.FilterSelector(
            filter=__import__("qdrant_client").models.Filter()), wait=True)
        self.llm = FakeLLM(type(self).script)
        self.llm.__enter__()
        self.addCleanup(self.llm.__exit__, None, None, None)
        with self.sessions() as db:
            settings.save(db, "llm", {"base_url": self.llm.base_url, "model": "fake-model", "context_window": 32768}, actor="t")
            db.commit()
        env = {"DATABASE_URL": self.db_url, "DATA_DIR": str(self.data_dir), "TEMP_DIR": str(self.tmp / "t"),
               "QDRANT_URL": base.URL, "QDRANT_API_KEY": base.KEY, "QDRANT_COLLECTION": base.COLLECTION, "QK3_EMBEDDER": "hash",
               "QK3_EMBEDDER_DIM": str(DIM), "APP_ENV": "development"}
        self.pool = AgentPool(env=env)
        self.addCleanup(self.pool.close_all)
        app = self.client.app
        app.state.agent_pool, app.state.session_factory = self.pool, self.sessions

    # ----- helpers -----
    def new_session(self, who="cong_binh") -> str:
        reply = self.client.post("/api/chat/sessions", headers=self.headers(who), json={})
        self.assertEqual(reply.status_code, 201, reply.text)
        return reply.json()["id"]

    def ask(self, who: str, session_id: str, text: str, **extra) -> list[tuple[str, dict]]:
        events: list[tuple[str, dict]] = []
        with self.client.stream("POST", f"/api/chat/sessions/{session_id}/messages", headers=self.headers(who),
                                json={"text": text, **extra}) as reply:
            self.assertEqual(reply.status_code, 200, reply.read())
            name = ""
            for line in reply.iter_lines():
                if line.startswith("event: "):
                    name = line[7:]
                elif line.startswith("data: "):
                    events.append((name, json.loads(line[6:])))
        return events

    @staticmethod
    def kinds(events) -> list[str]:
        return [name for name, _ in events]


class AskTest(ChatTestCase):
    @staticmethod
    def script(messages, tools):
        results = tool_results(messages)
        if turn_step(messages) == 0:
            return {"reasoning": "Cần tìm quyết định về Ban Chỉ đạo.", "tool_calls": [
                {"name": "mcp__qk3__search_documents", "arguments": {"query": "Ban Chỉ đạo", "mode": "keyword"}},
                {"name": "mcp__qk3__list_documents", "arguments": {}}]}
        cites = [r["cite"] for r in results if isinstance(r, dict) and "cite" in r]
        known = f"[{cites[0]}] " if cites else ""
        return {"reasoning": "Đã có kết quả.", "content": f"Quyết định kiện toàn Ban Chỉ đạo {known}và một mã bịa [999#1]."}

    def test_answer_cites_a_real_source_and_streams_steps(self):
        doc_id = self.upload_and_process("cong_binh")
        sid = self.new_session()
        events = self.ask("cong_binh", sid, "Ban Chỉ đạo được kiện toàn theo văn bản nào?")
        kinds = self.kinds(events)
        self.assertEqual(kinds[0], "session")
        self.assertEqual(kinds[-1], "done", kinds)
        self.assertIn("answer", kinds)
        steps = {}
        for name, data in events:
            if name == "step":
                steps[data["step"]["id"]] = data["step"]
        tools = [s["tool"] for s in steps.values() if s["kind"] == "tool"]
        self.assertEqual(sorted(tools), ["list_documents", "search_documents"])  # both called in one model step
        self.assertTrue(all(s["status"] == "done" for s in steps.values()), steps)
        self.assertTrue(any(s["kind"] == "thinking" for s in steps.values()))
        answer = dict(events)["answer"]
        self.assertIn("[1]", answer["text"])
        self.assertNotIn("999", answer["text"])  # an invented code is dropped
        (citation,) = answer["citations"]
        self.assertEqual((citation["doc_id"], citation["kind"], citation["readable"]), (str(doc_id), "store", True))
        self.assertEqual(citation["ref"], "15/QĐ-QK3")
        self.assertEqual(citation["unit_name"], "Phòng Công binh")

        detail = self.client.get(f"/api/chat/sessions/{sid}", headers=self.headers("cong_binh")).json()
        self.assertEqual([m["role"] for m in detail["messages"]], ["user", "assistant"])
        saved = detail["messages"][1]
        self.assertEqual((saved["status"], saved["content"]), ("done", answer["text"]))
        self.assertTrue(detail["session"]["title"].startswith("Ban Chỉ đạo được kiện toàn"))

    def test_the_assistant_only_sees_what_the_asker_may_read(self):
        self.upload_and_process("cong_binh")
        sid = self.new_session("hau_can")
        events = self.ask("hau_can", sid, "Ban Chỉ đạo?")
        self.assertEqual(dict(events)["answer"]["citations"], [])  # no tool result carried a cite, so the unknown code is dropped

    def test_other_users_cannot_open_or_use_a_conversation(self):
        sid = self.new_session("cong_binh")
        for method, url in (("get", f"/api/chat/sessions/{sid}"), ("delete", f"/api/chat/sessions/{sid}")):
            self.assertEqual(getattr(self.client, method)(url, headers=self.headers("hau_can")).status_code, 404)
        self.assertEqual(self.client.post(f"/api/chat/sessions/{sid}/messages", headers=self.headers("hau_can"), json={"text": "x"}).status_code, 404)


class StopTest(ChatTestCase):
    @staticmethod
    def script(messages, tools):
        return {"reasoning": "Đang cân nhắc.", "content": "Câu trả lời rất dài. " * 20}

    def test_stop_ends_the_turn_and_the_conversation_carries_on(self):
        import threading
        import time
        self.llm.delay, self.llm.piece_chars = 0.3, 4  # the model "speaks" for about a minute
        sid = self.new_session()
        box: list = []
        worker = threading.Thread(target=lambda: box.append(self.ask("cong_binh", sid, "Hãy trả lời thật dài")))
        worker.start()
        deadline = time.monotonic() + 60
        while not self.llm.requests and time.monotonic() < deadline:
            time.sleep(0.2)
        self.assertTrue(self.llm.requests, "the model was never called")
        busy = self.client.post(f"/api/chat/sessions/{sid}/messages", headers=self.headers("cong_binh"), json={"text": "đồng thời"})
        self.assertEqual(busy.status_code, 409)  # one answer at a time per conversation
        self.assertEqual(self.client.post(f"/api/chat/sessions/{sid}/stop", headers=self.headers("cong_binh")).status_code, 204)
        worker.join(30)
        self.assertFalse(worker.is_alive())
        events = box[0]
        self.assertEqual(events[-1][0], "done")
        self.assertEqual(events[-1][1]["status"], "stopped")
        self.assertNotIn("answer", self.kinds(events))
        detail = self.client.get(f"/api/chat/sessions/{sid}", headers=self.headers("cong_binh")).json()
        self.assertEqual([(m["role"], m["status"]) for m in detail["messages"]], [("user", "done"), ("assistant", "stopped")])

        self.llm.delay, self.llm.piece_chars = 0.0, 12
        again = self.ask("cong_binh", sid, "Trả lời ngắn thôi")
        self.assertEqual(self.kinds(again)[-1], "done")
        self.assertEqual(again[-1][1]["status"], "done")


class ReasoningFieldTest(ChatTestCase):
    """The model's thinking is shown whichever name the server gives the field (vLLM: "reasoning", SGLang/llama.cpp: "reasoning_content")."""

    @staticmethod
    def script(messages, tools):
        return {"reasoning": "Cân nhắc câu hỏi đơn giản.", "content": "Xin chào đồng chí."}

    def thinking_texts(self, field: str) -> list[str]:
        self.llm.reasoning_field = field
        events = self.ask("cong_binh", self.new_session(), "Chào")
        return [d["step"]["detail"]["text"] for n, d in events if n == "step" and d["step"]["kind"] == "thinking"]

    def test_vllm_style_field(self):
        self.assertEqual(self.thinking_texts("reasoning"), ["Cân nhắc câu hỏi đơn giản."])

    def test_sglang_style_field(self):
        self.assertEqual(self.thinking_texts("reasoning_content"), ["Cân nhắc câu hỏi đơn giản."])


class NotConfiguredTest(ChatTestCase):
    def test_missing_model_is_reported_not_crashed(self):
        with self.sessions() as db:
            settings.save(db, "llm", {"base_url": "", "model": ""}, actor="t")
            db.commit()
        events = self.ask("cong_binh", self.new_session(), "Xin chào")
        self.assertEqual(self.kinds(events)[-2:], ["error", "done"])
        self.assertIn("Chưa cấu hình", dict(events)["error"]["message"])


class RetryTest(ChatTestCase):
    def test_a_conversation_recovers_after_its_first_turn_failed(self):
        good = self.llm.base_url
        with self.sessions() as db:
            settings.save(db, "llm", {"base_url": "http://127.0.0.1:9/v1", "model": "fake-model"}, actor="t")
            db.commit()
        sid = self.new_session()
        first = self.ask("cong_binh", sid, "Xin chào")
        self.assertIn("error", self.kinds(first))
        with self.sessions() as db:
            settings.save(db, "llm", {"base_url": good, "model": "fake-model"}, actor="t")
            db.commit()
        second = self.ask("cong_binh", sid, "Xin chào lại")
        self.assertEqual(second[-1][1]["status"], "done", second)
        self.assertIn("answer", self.kinds(second))


class AttachmentTest(ChatTestCase):
    @staticmethod
    def script(messages, tools):
        results = tool_results(messages)
        if turn_step(messages) == 0:
            return {"tool_calls": [{"name": "mcp__qk3__search_attachments", "arguments": {"query": "Ban Chỉ đạo", "mode": "keyword"}}]}
        cites = [r["cite"] for r in results if isinstance(r, dict) and "cite" in r]
        return {"content": f"Tệp nói về kiện toàn Ban Chỉ đạo {f'[{cites[0]}]' if cites else ''}."}

    def test_attached_file_is_searchable_in_its_own_conversation_only(self):
        sid, other = self.new_session(), self.new_session("hau_can")
        path = self.sample("dinhkem.docx")
        with open(path, "rb") as fh:
            reply = self.client.post(f"/api/chat/sessions/{sid}/attachments", headers=self.headers("cong_binh"), files={"file": ("dinhkem.docx", fh, base.DOCX)})
        self.assertEqual(reply.status_code, 201, reply.text)
        attachment = reply.json()
        self.assertEqual(attachment["state"], "queued")
        premature = self.client.post(f"/api/chat/sessions/{sid}/messages", headers=self.headers("cong_binh"),
                                     json={"text": "Tệp nói gì?", "attachment_ids": [attachment["id"]]})
        self.assertEqual(premature.status_code, 422)  # not processed yet
        self.work()
        ready = self.client.get(f"/api/chat/sessions/{sid}/attachments/{attachment['id']}", headers=self.headers("cong_binh")).json()
        self.assertEqual(ready["state"], "ready", ready)
        self.assertGreater(ready["chunk_count"], 0)
        # not reachable from another user's conversation
        self.assertEqual(self.client.get(f"/api/chat/sessions/{other}/attachments/{attachment['id']}", headers=self.headers("hau_can")).status_code, 404)

        events = self.ask("cong_binh", sid, "Tệp nói gì?", attachment_ids=[attachment["id"]])
        answer = dict(events)["answer"]
        (citation,) = answer["citations"]
        self.assertEqual((citation["kind"], citation["doc_id"]), ("attachment", f"att{attachment['id']}"))
        content = self.client.get(f"/api/chat/sessions/{sid}/attachments/{attachment['id']}/content", headers=self.headers("cong_binh"))
        self.assertEqual(content.status_code, 200)
        self.assertGreater(len(content.json()), 5)

        other_events = self.ask("hau_can", other, "Tệp nói gì?")  # same tool, other conversation: nothing found
        self.assertEqual(dict(other_events)["answer"]["citations"], [])

        self.assertTrue(list((self.data_dir / "dsh").glob(f"sessions/*/{sid}*")))  # the harness kept a transcript
        self.assertEqual(self.client.delete(f"/api/chat/sessions/{sid}", headers=self.headers("cong_binh")).status_code, 204)
        with self.sessions() as db:
            self.assertEqual(db.query(ChatAttachment).count(), 0)
            self.assertEqual(db.query(ChatMessage).count(), 2)  # only the other user's pair
        self.assertEqual(ATT_INDEX.count(f"att{attachment['id']}"), 0)
        self.assertEqual(list((self.data_dir / "dsh").glob(f"sessions/*/{sid}*")), [])  # the agent's transcript goes too


class CanvasTest(ChatTestCase):
    @staticmethod
    def script(messages, tools):
        step = turn_step(messages)
        if step == 0:
            return {"reasoning": "Mở mẫu công văn.", "tool_calls": [{"name": "mcp__qk3__canvas_create", "arguments": {"kind": "CV"}}]}
        if step == 1:
            return {"tool_calls": [{"name": "mcp__qk3__canvas_style", "arguments": {"topic": "tập huấn"}}]}
        if step == 2:
            return {"tool_calls": [
                {"name": "mcp__qk3__canvas_set_fields", "arguments": {"fields": {
                    "trich_yeu": "tổ chức tập huấn năm 2026", "kinh_gui": "Các đơn vị trực thuộc",
                    "noi_nhan": "- Như trên;\n- Lưu: VT, TC. A5.", "co_quan_ban_hanh": "PHÒNG KHÁC"}}},
                {"name": "mcp__qk3__canvas_set_content", "arguments": {"blocks": [
                    {"kind": "para", "text": "Thực hiện kế hoạch huấn luyện năm 2026, Phòng triển khai tập huấn như sau:"},
                    {"kind": "item", "text": "- Thời gian: từ ngày 10/6/2026 đến ngày 20/6/2026."}]}}]}
        if step == 3:
            ids = next(item["block_ids"] for item in tool_results(messages) if isinstance(item, dict) and "block_ids" in item)
            return {"tool_calls": [{"name": "mcp__qk3__canvas_edit_block", "arguments": {
                "action": "replace", "block_id": ids[0], "note": "viết lại",
                "text": "Đảm bảo hoàn thành 18/20 nhiệm vụ trước ngày 15/3/2026."}}]}
        if step == 4:
            return {"tool_calls": [{"name": "mcp__qk3__canvas_check", "arguments": {}}]}
        return {"content": "Đã soạn công văn; còn thiếu người ký và chức vụ."}

    def test_drafting_reaches_the_canvas_and_respects_ownership(self):
        sid = self.new_session()
        events = self.ask("cong_binh", sid, "Soạn công văn tổ chức tập huấn", canvas=True)
        self.assertEqual(self.kinds(events)[-1], "done", events[-3:])
        canvases = [d["draft"] for n, d in events if n == "canvas"]
        self.assertGreaterEqual(len(canvases), 2)  # after opening and after editing
        draft = canvases[-1]
        self.assertEqual(draft["template"]["name"], "Công văn")
        self.assertEqual(draft["fields"]["trich_yeu"]["text"], "tổ chức tập huấn năm 2026")
        self.assertEqual(draft["fields"]["co_quan_ban_hanh"]["text"], "BỘ THAM MƯU")  # the assistant's override was refused
        styled = [d["step"] for n, d in events if n == "step" and d["step"]["tool"] == "canvas_style"]
        self.assertEqual([s["status"] for s in styled][-1:], ["done"], styled)
        self.assertEqual([b["kind"] for b in draft["blocks"]], ["para", "item"])
        checks = draft["blocks"][0]["proposal"]["checks"]
        self.assertTrue(any(item["message"].startswith("Có thêm '18/20'") for item in checks), checks)
        self.assertTrue(any("bảo đảm" in item["message"] for item in checks), checks)
        self.assertIn("nguoi_ky", draft["missing"])
        self.assertEqual(draft["history"][-1]["by"], "assistant")

        headers = self.headers("cong_binh")
        url = f"/api/chat/sessions/{sid}/draft"
        self.assertEqual(self.client.get(url, headers=headers).json()["version"], draft["version"])
        edited = self.client.patch(url, headers=headers, json={"fields": {"nguoi_ky": "Đại tá Nguyễn Văn A", "quyen_han": "TRƯỞNG PHÒNG"},
                                                               "blocks": [{"id": draft["blocks"][0]["id"], "text": "Đoạn người dùng sửa."}]})
        self.assertEqual(edited.status_code, 200, edited.text)
        self.assertEqual(edited.json()["blocks"][0]["owner"], "user")
        self.assertEqual(self.client.patch(url, headers=headers, json={"fields": {"khong_co": "x"}}).status_code, 422)
        check = self.client.post(url + "/check", headers=headers).json()
        self.assertEqual(check["counts"]["error"], 0, check["findings"])
        export = self.client.get(url + "/export", headers=headers)
        self.assertEqual((export.status_code, export.content[:2]), (200, b"PK"))
        saved = self.client.post(url + "/save", headers=headers, json={})
        self.assertEqual(saved.status_code, 201, saved.text)
        self.assertTrue(saved.json()["document"]["original_name"].endswith(".docx"))
        self.assertEqual(self.client.get(url, headers=self.headers("hau_can")).status_code, 404)
        self.assertEqual(self.client.delete(url, headers=headers).status_code, 204)
        self.assertIsNone(self.client.get(url, headers=headers).json())


class CanvasTableTest(ChatTestCase):
    @staticmethod
    def script(messages, tools):
        step = turn_step(messages)
        if step == 0:
            return {"tool_calls": [{"name": "mcp__qk3__canvas_create", "arguments": {"kind": "CV"}}]}
        if step == 1:
            return {"tool_calls": [{"name": "mcp__qk3__canvas_set_content", "arguments": {"blocks": [
                {"kind": "para", "text": "Đề nghị bổ sung trang thiết bị, tổng kinh phí 75.000.000 đồng, chi tiết tại Phụ lục kèm theo."},
                {"kind": "appendix", "text": "Danh mục trang thiết bị"},
                {"kind": "table", "table": {
                    "columns": [{"id": "c1", "label": "TT"}, {"id": "c2", "label": "Tên trang bị"}, {"id": "c3", "label": "Số lượng"},
                                {"id": "c4", "label": "Đơn giá"}, {"id": "c5", "label": "Thành tiền", "formula": "c3 * c4"}],
                    "rows": [{"cells": ["1", "Máy tính", "5", "15.000.000"]}, {"cells": ["2", "Máy in", "…", "4.500.000"]},
                             {"type": "total", "cells": ["", "Cộng"], "sum": ["c3", "c5"]}]}}]}}]}
        if step == 2:
            ids = next(item["block_ids"] for item in tool_results(messages) if isinstance(item, dict) and "block_ids" in item)
            return {"tool_calls": [{"name": "mcp__qk3__canvas_edit_table", "arguments": {
                "block_id": ids[2], "base_version": 1, "note": "thêm máy quét",
                "ops": [{"op": "insert_row", "after": "r2", "cells": ["3", "Máy quét", "2", "6.000.000"]},
                        {"op": "set", "row": "r1", "column": "c3", "value": "6"}]}}]}
        if step == 3:
            edited = next(item for item in tool_results(messages) if isinstance(item, dict) and "notes" in item)
            assert edited["notes"] == ["Thêm dòng r4."], edited
            return {"tool_calls": [{"name": "mcp__qk3__canvas_edit_table", "arguments": {  # stale version: refused
                "block_id": edited["block_id"], "base_version": 7, "ops": [{"op": "delete_row", "row": "r1"}]}}]}
        refusal = next(m for m in reversed(messages) if m["role"] == "tool")["content"]
        refusal = refusal if isinstance(refusal, str) else "".join(p.get("text", "") for p in refusal)
        assert "phiên bản hiện tại 1" in refusal and "canvas_read" in refusal, refusal  # the model is told to read again
        return {"content": "Đã đề xuất thêm máy quét; còn thiếu số lượng máy in."}

    def test_the_assistant_edits_a_table_by_id_and_the_user_decides(self):
        sid = self.new_session()
        events = self.ask("cong_binh", sid, "Lập bảng trang thiết bị", canvas=True)
        self.assertEqual(self.kinds(events)[-1], "done", events[-3:])
        edits = {d["step"]["id"]: d["step"]["status"] for n, d in events if n == "step" and d["step"]["tool"] == "canvas_edit_table"}
        self.assertEqual(list(edits.values()), ["done", "error"], edits)
        draft = [d["draft"] for n, d in events if n == "canvas"][-1]
        table = next(b for b in draft["blocks"] if b["kind"] == "table")
        # the printer's quantity is missing: its amount and both totals wait for it too
        self.assertEqual((table["version"], table["landscape"], table["blanks"]), (1, False, 4))
        proposed = table["proposal"]["table"]
        self.assertEqual([row["id"] for row in proposed["rows"]], ["r1", "r2", "r4", "r3"])
        self.assertEqual(proposed["rows"][2]["cells"][4], "12.000.000")  # worked out by the table, not the model
        self.assertEqual(proposed["rows"][3]["cells"][2], "…")  # the total waits for the missing figure

        headers = self.headers("cong_binh")
        url = f"/api/chat/sessions/{sid}/draft"
        accepted = self.client.post(f"{url}/blocks/{table['id']}/accept", headers=headers).json()
        para = accepted["blocks"][0]
        self.assertEqual(para["stale"]["figures"], ["75.000.000"])  # 5 × 15.000.000 became 6 × 15.000.000
        spec = next(b for b in accepted["blocks"] if b["id"] == table["id"])["table"]
        spec["rows"][1]["cells"][2] = "1"
        edited = self.client.patch(url, headers=headers, json={"blocks": [{"id": table["id"], "table": spec}],
                                                               "reviewed": [para["id"]]})
        self.assertEqual(edited.status_code, 200, edited.text)
        mine = next(b for b in edited.json()["blocks"] if b["id"] == table["id"])
        self.assertEqual((mine["version"], mine["owner"], mine["blanks"]), (3, "user", 0))
        self.assertEqual(mine["table"]["rows"][3]["cells"][4], "106.500.000")  # 90 + 4,5 + 12 million
        self.assertNotIn("stale", edited.json()["blocks"][0])


if __name__ == "__main__":
    unittest.main()
