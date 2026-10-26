import unittest

from sqlalchemy import select

from app.models import AuditLog
from app.moderation import check, model
from app.services import settings
from test_chat_api import ChatTestCase, setUpModule, tearDownModule  # noqa: F401  (the shared index collection)


class RulesTest(unittest.TestCase):
    def level(self, text: str) -> str:
        return check(text).level

    def test_profanity_in_the_ways_people_type_it(self):
        for text in ["từ đjt mẹ phát", "Địt mẹ mày", "dit me", "d i t m e", "địttttt mẹeeee", "d1t me", "đ*t mẹ", "đ.m", "dmmmmm", "lồn"]:
            self.assertEqual(self.level(text), "severe", text)

    def test_mild_words_are_mild(self):
        for text in ["vcl quá", "báo cáo vl", "thằng ngu này"]:
            self.assertEqual(self.level(text), "mild", text)

    def test_threats_and_discrimination(self):
        self.assertEqual(check("tao giết mày").categories, ["de_doa"])
        self.assertEqual(check("bọn mọi").categories, ["ky_thi"])

    def test_ordinary_military_and_administrative_language_passes(self):
        for text in ["các đơn vị báo cáo", "uống lon bia", "đít xe", "cc: phòng tham mưu", "Tiêu diệt mục tiêu địch", "con chó nghiệp vụ của đại đội",
                     "mọi người cùng tham gia", "Điều 3 Quyết định số 18/QĐ-QK3", "kích thước 5 dm x 3 dm", "Số 1150 ngày 3/4", "a b c d e f",
                     "Trung đoàn 1, đại đội 3 4 5 7", "Tổ chức tập huấn công tác tác chiến năm 2026", "bắn đạn thật, đánh chiếm cao điểm"]:
            self.assertEqual(self.level(text), "none", text)

    def test_the_excerpt_is_short(self):
        hit = check("a " * 80 + "địt mẹ" + " b" * 80).hits[0]
        self.assertLess(len(hit.excerpt), 120)


@unittest.skipUnless(model.available(), "no classifier files in MODERATION_MODEL_DIR (tools/export_moderation_model.py)")
class ClassifierTest(unittest.TestCase):
    def toxic(self, text: str) -> float:
        return model.get().scores([text])[0].toxic

    def test_insults_without_a_listed_word_are_seen(self):
        self.assertGreater(self.toxic("dân tộc X toàn lũ ăn bám"), 0.9)

    def test_ordinary_language_stays_under_the_default_threshold(self):
        """Short out-of-domain text can score around 0.5 (the model was trained on comments), hence the 0.95 default."""
        for text in ["Kế hoạch huấn luyện năm 2026 của Bộ Tham mưu", "Tiêu diệt mục tiêu địch ở cao điểm 305", "Quyết định về việc xử lý kỷ luật đồng chí vi phạm",
                     "Điều 3. Quyết định này có hiệu lực kể từ ngày ký."]:
            self.assertLess(self.toxic(text), 0.95, text)

    def test_service_dogs_are_not_an_insult(self):
        from app.moderation.policy import _SERVICE_TERMS
        text = _SERVICE_TERMS.sub("khuyển", "Con chó nghiệp vụ của đại đội trinh sát")
        self.assertLess(self.toxic(text), 0.95)

    def test_a_long_message_is_cut_into_windows(self):
        scores = model.get().scores(["Báo cáo kết quả huấn luyện. " * 300, "ngắn"])
        self.assertEqual(len(scores), 2)


@unittest.skipUnless(model.available(), "no classifier files in MODERATION_MODEL_DIR")
class ClassifierPolicyTest(ChatTestCase):
    def test_a_model_only_finding_is_a_mild_warning(self):
        events = self.ask("cong_binh", self.new_session(), "dân tộc X toàn lũ ăn bám, chỉ biết chờ cứu trợ")
        self.assertEqual(self.kinds(events)[:2], ["session", "moderation"])
        with self.sessions() as db:
            row = db.scalars(select(AuditLog).where(AuditLog.action == "moderation.warn")).one()
        self.assertIn("model:", row.detail)


class PolicyTest(ChatTestCase):
    def trail(self) -> list[AuditLog]:
        with self.sessions() as db:
            return list(db.scalars(select(AuditLog).where(AuditLog.action.like("moderation.%")).order_by(AuditLog.id)))

    def test_severe_message_is_refused_and_traced(self):
        sid = self.new_session()
        reply = self.client.post(f"/api/chat/sessions/{sid}/messages", headers=self.headers("cong_binh"), json={"text": "từ đjt mẹ phát"})
        self.assertEqual(reply.status_code, 422)
        self.assertEqual(reply.json()["code"], "moderation")
        self.assertIn("chưa được gửi", reply.json()["detail"])
        (row,) = self.trail()
        self.assertEqual((row.action, row.username, row.entity_type, row.entity_id), ("moderation.block", "congbinh", "chat", sid))
        self.assertIn("Lần thứ 1", row.detail)
        self.assertEqual(self.llm.requests, [])  # nothing reached the model

    def test_a_second_attempt_is_counted(self):
        sid = self.new_session()
        for _ in range(2):
            self.client.post(f"/api/chat/sessions/{sid}/messages", headers=self.headers("cong_binh"), json={"text": "dit me"})
        self.assertIn("Lần thứ 2", self.trail()[-1].detail)

    def test_mild_message_is_sent_with_a_warning(self):
        events = self.ask("cong_binh", self.new_session(), "thằng ngu này làm gì thế")
        self.assertEqual(self.kinds(events)[:2], ["session", "moderation"])
        notice = dict(events)["moderation"]
        self.assertEqual((notice["action"], notice["level"], notice["count"]), ("warn", "mild", 1))
        self.assertEqual(self.kinds(events)[-1], "done")
        self.assertEqual(self.trail()[0].action, "moderation.warn")

    def test_log_only_policy_is_silent_to_the_user(self):
        with self.sessions() as db:
            settings.save(db, "moderation", {"mild_action": "log"}, actor="t")
            db.commit()
        events = self.ask("cong_binh", self.new_session(), "vcl")
        self.assertNotIn("moderation", self.kinds(events))
        self.assertEqual(self.trail()[0].action, "moderation.log")

    def test_switched_off_means_no_check_and_no_trace(self):
        with self.sessions() as db:
            settings.save(db, "moderation", {"enabled": False}, actor="t")
            db.commit()
        events = self.ask("cong_binh", self.new_session(), "dit me")
        self.assertNotIn("moderation", self.kinds(events))
        self.assertEqual(self.trail(), [])

    def test_an_ordinary_question_leaves_no_trace(self):
        events = self.ask("cong_binh", self.new_session(), "Tóm tắt quyết định về Ban Chỉ đạo")
        self.assertNotIn("moderation", self.kinds(events))
        self.assertEqual(self.trail(), [])


if __name__ == "__main__":
    unittest.main()
