"""Dashboard figures: who may see them, what they cover, and that they add up."""
from datetime import timedelta

from sqlalchemy import select

from app.models import AuditLog, DraftRevision, User
from app.models.base import now_utc
from app.services import users
from test_documents_api import PASSWORD, ApiTestCase, setUpModule, tearDownModule  # noqa: F401  (the shared index collection)


class StatsTest(ApiTestCase):
    def setUp(self):
        super().setUp()
        with self.sessions() as db:
            users.create(db, username="chihuy_btm", password=PASSWORD, full_name="Chỉ huy Bộ Tham mưu", unit_id="btm", role="commander")
            users.create(db, username="chinhtri", password=PASSWORD, full_name="Chính trị", unit_id="cct", role="staff")
            db.commit()
        self.tokens["btm_commander"] = {"Authorization": "Bearer " + self.client.post(
            "/api/auth/login", json={"username": "chihuy_btm", "password": PASSWORD}).json()["access_token"]}
        self.tokens["chinh_tri"] = {"Authorization": "Bearer " + self.client.post(
            "/api/auth/login", json={"username": "chinhtri", "password": PASSWORD}).json()["access_token"]}

    def ask_audit(self, username: str, action: str = "chat.ask", ago: timedelta = timedelta(hours=1)) -> None:
        with self.sessions() as db:
            user = db.scalar(select(User).where(User.username == username))
            db.add(AuditLog(user_id=user.id, username=username, action=action, created_at=now_utc() - ago))
            db.commit()

    def stats(self, who: str, **params):
        return self.client.get("/api/stats", headers=self.headers(who), params=params)

    def test_only_admin_and_commander_may_look(self):
        self.assertEqual(self.stats("cong_binh").status_code, 403)
        self.assertEqual(self.stats("bo_tham_muu").status_code, 403)
        self.assertEqual(self.client.get("/api/stats").status_code, 401)
        self.assertEqual(self.stats("admin").status_code, 200)
        self.assertEqual(self.stats("commander").status_code, 200)

    def test_a_commander_sees_only_their_branch_an_admin_everything(self):
        self.upload_and_process("cong_binh")
        self.upload_and_process("hau_can", number="12")
        self.upload_and_process("chinh_tri")
        everything = self.stats("admin").json()
        self.assertEqual(everything["totals"]["documents"], 3)
        self.assertTrue(everything["scope"]["everything"])
        branch = self.stats("btm_commander").json()
        self.assertEqual(branch["totals"]["documents"], 2)
        self.assertEqual({row["unit_id"] for row in branch["by_unit"]}, {"btm.cong_binh", "btm.hau_can"})
        self.assertEqual({row["branch_id"] for row in branch["by_unit"]}, {"btm"})
        self.assertEqual(branch["scope"]["unit_id"], "btm")
        self.assertEqual(sum(i["count"] for i in branch["by_state"]), 2)

    def test_the_parts_add_up(self):
        self.upload_and_process("cong_binh")
        data = self.stats("admin").json()
        total = data["totals"]["documents"]
        self.assertEqual(sum(i["count"] for i in data["by_state"]), total)
        self.assertEqual(sum(i["count"] for i in data["by_level"]), total)
        self.assertEqual(sum(i["count"] for i in data["by_type"]), total)
        self.assertEqual(sum(u["count"] for u in data["by_unit"]), total)
        self.assertEqual(len(data["uploads_by_month"]), 12)
        self.assertEqual(data["uploads_by_month"][-1]["count"], total)

    def test_usage_counts_questions_by_day_and_unit(self):
        self.ask_audit("congbinh")
        self.ask_audit("congbinh", ago=timedelta(days=3))
        self.ask_audit("haucan", ago=timedelta(days=40))  # outside a 30-day period, inside 90
        self.ask_audit("chinhtri")
        self.ask_audit("congbinh", action="moderation.block")
        self.ask_audit("congbinh", action="auth.login_failed")
        data = self.stats("admin", days=30).json()
        self.assertEqual(data["days"], 30)
        self.assertEqual(len(data["questions_by_day"]), 30)
        self.assertEqual(sum(d["count"] for d in data["questions_by_day"]), 3)
        usage = {row["unit_id"]: row for row in data["usage_by_unit"]}
        self.assertEqual((usage["btm.cong_binh"]["questions"], usage["btm.cong_binh"]["moderation"], usage["btm.cong_binh"]["active_users"]), (2, 1, 1))
        self.assertEqual(sum(usage["btm.cong_binh"]["series"]), 2)
        self.assertEqual(usage["cct"]["questions"], 1)
        self.assertEqual(data["totals"]["moderation_period"], 1)
        self.assertEqual([i["key"] for i in data["moderation_by_action"]], ["block"])
        self.assertEqual(data["moderation_recent"][0]["username"], "congbinh")
        self.assertEqual(sum(d["count"] for d in self.stats("admin", days=90).json()["questions_by_day"]), 4)

    def test_a_commander_does_not_see_other_branches_usage(self):
        self.ask_audit("congbinh")
        self.ask_audit("chinhtri")
        data = self.stats("btm_commander").json()
        self.assertEqual(data["totals"]["questions_period"], 1)
        self.assertNotIn("cct", {row["unit_id"] for row in data["usage_by_unit"]})
        self.assertEqual(data["totals"]["users"], 4)  # chihuy_btm, congbinh, haucan, btm: the accounts under Bộ Tham mưu

    def test_canvas_counts_stay_inside_the_viewers_branch(self):
        with self.sessions() as db:
            cong = db.scalar(select(User).where(User.username == "congbinh"))
            other = db.scalar(select(User).where(User.username == "chinhtri"))
            db.add(DraftRevision(session_id="s", user_id=cong.id, unit_id=cong.unit_id, template="M08", block_id="b1",
                                 outcome="accepted", before="a", proposed="b", final="b"))
            db.add(DraftRevision(session_id="s", user_id=cong.id, unit_id=cong.unit_id, template="M08", block_id="b1",
                                 outcome="edited_after", before="b", proposed="b", final="c"))
            db.add(DraftRevision(session_id="t", user_id=other.id, unit_id=other.unit_id, template="M08", block_id="b1",
                                 outcome="rejected", before="a", proposed="b", final="a"))
            db.commit()
        branch = self.stats("btm_commander").json()["canvas"]
        self.assertEqual((branch["proposals"], branch["accepted"], branch["rejected"], branch["edited_after"]), (1, 1, 0, 1))
        whole = self.stats("admin").json()["canvas"]
        self.assertEqual((whole["proposals"], whole["rejected"]), (2, 1))

    def test_an_unknown_period_falls_back_to_thirty_days(self):
        self.assertEqual(self.stats("admin", days=5).json()["days"], 30)
