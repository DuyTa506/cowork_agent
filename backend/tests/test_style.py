"""Writing style: what a document shows of it (read from its index chunks), the unit profiles built from many documents, the
header and guide a draft gets from them, and the example documents found in the user's scope."""
import json
import os
import tempfile
import unittest
import uuid
from datetime import date
from pathlib import Path
from unittest import mock

from qdrant_client import QdrantClient

from app.drafting import style, style_mining, templates
from app.drafting.content import DraftContent, Issuer
from app.models import ChatSession, User
from app.org import Principal, UnitTree, place_upload, scope_for
from app.parsing import Metadata, ParsedDocument, Section
from app.parsing.chunker import chunk_document
from app.parsing.models import Block
from app.search import HashEmbedder, QdrantIndex
from app.services import chat, drafts
from support import memory_session

URL = os.getenv("QDRANT_URL", "http://127.0.0.1:6333")
KEY = os.getenv("QDRANT_API_KEY", "ChangeQdrantKey_2026")
TREE = UnitTree.load()
KH, CV = templates.get("KH"), templates.get("CV")
TTM = "KT. THAM MƯU TRƯỞNG PHÓ THAM MƯU TRƯỞNG"


def document(kind="Kế hoạch", *, symbol="KH-TM", issuing="BỘ THAM MƯU", parent="QUÂN KHU 3", day="2026-05-04", topic="huấn luyện",
             luu="KHQS", recipients=("Các phòng, ban thuộc Bộ Tham mưu",), opening="",
             closing="Nhận được kế hoạch, các cơ quan, đơn vị triển khai thực hiện nghiêm túc./.", appendix=False) -> ParsedDocument:
    opening = opening or (f"Thực hiện Kế hoạch số 12/KH-QK3 ngày 02/01/2026 của Bộ Tư lệnh Quân khu về công tác {topic} năm 2026, "
                          "Bộ Tham mưu xây dựng kế hoạch như sau:")
    sections = [
        Section("roman", "I", "I. MỤC ĐÍCH, YÊU CẦU", 2, children=[
            Section("number", "1", "1. Mục đích", 3, [Block("para", f"Nâng cao chất lượng công tác {topic} của cơ quan, đơn vị.", 4)]),
            Section("number", "2", "2. Yêu cầu", 5, [Block("para", "Bảo đảm an toàn tuyệt đối về người và vũ khí trang bị.", 6)])]),
        Section("roman", "II", "II. NỘI DUNG", 7, [Block("para", f"Tổ chức {topic} theo đúng chương trình đã được phê duyệt.", 8)]),
        Section("roman", "III", "III. TỔ CHỨC THỰC HIỆN", 9, [Block("para", closing, 10)]),
    ]
    if appendix:
        sections.append(Section("upper", "", "PHỤ LỤC", 11, [Block("para", "Bảng tổng hợp số liệu chi tiết của các đơn vị tham gia.", 12)]))
    meta = Metadata(doc_type=kind, number="9", symbol=symbol, date=day, parent_agency=parent, issuing_agency=issuing,
                    title=f"Công tác {topic}", distribution=[*recipients, f"Lưu: VT, {luu}. A5"], signer_role=TTM,
                    signer_name="Đại tá Nguyễn Văn A")
    return ParsedDocument("x.docx", "docx", meta, Section("root", blocks=[Block("para", opening, 1)], children=sections))


def payloads(doc_id, doc, unit, level="thuong"):
    """The chunk payloads the index stores for `doc` (the fields the miner reads)."""
    meta = doc.metadata
    base = {"doc_id": doc_id, "unit_id": unit, "level": level, "doc_type": meta.doc_type, "symbol": meta.symbol,
            "issuing_agency": meta.issuing_agency, "date": meta.date}
    return [{**base, "chunk_index": c.index, "part": c.part, "text": c.text} for c in chunk_document(doc, doc_id)]


def sample(doc_id, doc, unit, **kw):
    return style_mining.sample(payloads(doc_id, doc, unit, **kw))


def corpus():
    """Bộ Tham mưu: Phòng KHQS (five plans, three công văn) and Phòng Công binh (three plans); Phòng Quân y of Cục HC-KT, whose
    agency was renamed."""
    out = [sample(f"khqs{i}", document(day=f"2023-0{i + 1}-10", topic=t,
                                       recipients=("Các phòng, ban thuộc Bộ Tham mưu", *(["Đồng chí Nguyễn Văn B"] if i < 2 else []))),
                  "btm.khqs") for i, t in enumerate(("huấn luyện", "sáng kiến", "nghiên cứu khoa học", "tổng kết"))]
    # the newest plan went out under the Military Region's name: one document does not change the unit's usual header
    out.append(sample("khqs-qk", document(symbol="KH-QK3", issuing="QUÂN KHU 3", parent="BỘ QUỐC PHÒNG", day="2026-07-01"), "btm.khqs"))
    out += [sample(f"khqs-cv{i}", document("Công văn", symbol="TM-KHQS", day=f"2025-0{i + 1}-01",
                                           opening="Thực hiện ý kiến chỉ đạo của Thủ trưởng Bộ Tham mưu về công tác nghiên cứu, "
                                                   f"Phòng Khoa học quân sự đề nghị nội dung {i}."), "btm.khqs") for i in range(3)]
    out += [sample(f"cb{i}", document(topic=t, luu="CôB", recipients=("Các tiểu đoàn công binh",),
                                      closing="Các cơ quan, đơn vị căn cứ kế hoạch tổ chức thực hiện nghiêm túc, hiệu quả./."),
                   "btm.cong_binh") for i, t in enumerate(("rà phá bom mìn", "xây dựng công sự", "vượt sông"))]
    out += [sample(f"qy-old{i}", document("Công văn", symbol="HC-QY", issuing="CỤC HẬU CẦN", day=f"2023-0{i + 1}-01", luu="QY"),
                   "hckt.quan_y") for i in range(4)]
    out += [sample(f"qy-new{i}", document("Công văn", symbol="HCKT-QY", issuing="CỤC HẬU CẦN - KỸ THUẬT", day=f"2026-0{i + 1}-01",
                                          luu="QY"), "hckt.quan_y") for i in range(2)]
    return out


class SampleTest(unittest.TestCase):
    def test_reads_the_header_outline_and_formulas_of_a_document(self):
        s = sample("a", document(), "btm.khqs")
        self.assertEqual((s.kind, s.issuing_agency, s.parent_agency, s.signer_role, s.luu), ("Kế hoạch", "BỘ THAM MƯU", "QUÂN KHU 3", TTM, "KHQS"))
        self.assertEqual(s.recipients, ["Các phòng, ban thuộc Bộ Tham mưu"])
        self.assertEqual(s.outline, [("MỤC ĐÍCH, YÊU CẦU", ["Mục đích", "Yêu cầu"]), ("NỘI DUNG", []), ("TỔ CHỨC THỰC HIỆN", [])])
        self.assertTrue(s.opening.startswith("Thực hiện Kế hoạch số 12/KH-QK3"))
        self.assertEqual(s.closing, "Nhận được kế hoạch, các cơ quan, đơn vị triển khai thực hiện nghiêm túc")
        self.assertEqual(s.symbol_parts, ("TM", ""))
        self.assertEqual(sample("b", document("Công văn", symbol="TM-KHQS"), "btm.khqs").symbol_parts, ("TM", "KHQS"))
        self.assertEqual(s.passages[0][0], "MỤC ĐÍCH, YÊU CẦU")
        self.assertIn("Nâng cao chất lượng", s.passages[0][1])
        self.assertIn("Bảo đảm an toàn", s.passages[0][1])
        self.assertIn("Tổ chức huấn luyện", style.passage_of(s, "II. Nội dung"))
        self.assertEqual(style.passage_of(s, "không có mục này"), "")

    def test_appendix_is_not_part_of_the_style(self):
        s = sample("a", document(appendix=True), "btm.khqs")
        self.assertEqual(s.closing, "Nhận được kế hoạch, các cơ quan, đơn vị triển khai thực hiện nghiêm túc")
        self.assertNotIn("PHỤ LỤC", [h for h, _ in s.outline])

    def test_secret_documents_are_left_out(self):
        self.assertIsNone(sample("a", document(), "btm.khqs", level="mat"))
        self.assertIsNotNone(style_mining.sample(payloads("a", document(), "btm.khqs", level="mat"), keep_secret=True))

    def test_ocr_markup_is_cleaned(self):
        self.assertEqual(style_mining.clean("Số $^{(07)}$ ## **Kế hoạch** $\\mathcal{O}$"), "Số (07) Kế hoạch")


class BuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = style_mining.build(corpus(), TREE)
        cls.units = cls.data["units"]

    def test_header_follows_the_units_usual_documents(self):
        khqs = self.units["btm.khqs"]
        self.assertEqual((khqs["issuer"], khqs["luu"], khqs["drafter"]), ("btm", "KHQS", "KHQS"))
        self.assertEqual((khqs["kinds"]["Kế hoạch"]["issuer"], khqs["kinds"]["Kế hoạch"]["symbol"]), ("btm", "KH-TM"))
        self.assertEqual(khqs["kinds"]["Công văn"]["symbol"], "TM-KHQS")
        self.assertEqual(self.data["issuers"]["btm"], {"abbr": "TM", "owner": "QUÂN KHU 3"})

    def test_a_renamed_agency_follows_its_recent_documents(self):
        self.assertEqual(self.units["hckt.quan_y"]["kinds"]["Công văn"]["symbol"], "HCKT-QY")
        self.assertEqual(self.data["issuers"]["hckt"]["abbr"], "HCKT")

    def test_items_need_several_documents(self):
        recipients = [r for r, _ in self.units["btm.khqs"]["kinds"]["Kế hoạch"]["recipients"]]
        self.assertIn("Các phòng, ban thuộc Bộ Tham mưu", recipients)
        self.assertNotIn("Đồng chí Nguyễn Văn B", recipients)  # in two documents only
        outline = self.units["btm.khqs"]["kinds"]["Kế hoạch"]["outline"]
        self.assertEqual([o["heading"] for o in outline], ["MỤC ĐÍCH, YÊU CẦU", "NỘI DUNG", "TỔ CHỨC THỰC HIỆN"])
        self.assertEqual(outline[0]["sub"], ["Mục đích", "Yêu cầu"])

    def test_a_group_of_units_keeps_only_what_several_of_them_share(self):
        own = [t for t, _ in self.units["btm.khqs"]["kinds"]["Kế hoạch"]["closings"]]
        agency = self.units["btm"]["kinds"]["Kế hoạch"]
        self.assertTrue(any(t.startswith("Nhận được kế hoạch") for t in own))
        self.assertFalse(any(t.startswith("Nhận được kế hoạch") for t, _ in agency.get("closings", [])))  # Phòng KHQS's alone
        openings = [t for t, _ in agency["openings"]]
        self.assertTrue(any(t.startswith("Thực hiện Kế hoạch số …/KH-QK3 ngày … của Bộ Tư lệnh Quân khu về công tác") for t in openings), openings)


class IssuerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = style_mining.build(corpus(), TREE)

    def test_without_profiles_a_phong_issues_under_its_agency(self):
        self.assertEqual(style.issuer_for(TREE, "btm.tac_chien", CV, {}), Issuer("Bộ Tham mưu", "Quân khu 3"))
        self.assertEqual(style.issuer_for(TREE, "btm.d97", KH, {}), Issuer("Tiểu đoàn 97", "Bộ Tham mưu"))
        self.assertEqual(style.issuer_for(TREE, "btm.ban_tai_chinh", KH, {}).name, "Bộ Tham mưu")
        self.assertEqual(style.issuer_for(TREE, "khong_co", KH, {}), Issuer())

    def test_with_profiles_the_symbol_and_luu_line_are_the_units(self):
        self.assertEqual(style.issuer_for(TREE, "btm.khqs", KH, self.data),
                         Issuer("Bộ Tham mưu", "Quân khu 3", "KH-TM", "KHQS", "KT. THAM MƯU TRƯỞNG\nPHÓ THAM MƯU TRƯỞNG"))
        self.assertEqual(style.issuer_for(TREE, "btm.khqs", CV, self.data).symbol, "TM-KHQS")
        # Phòng Công binh has no công văn: the symbol is composed from the agency's abbreviation and the office's "Lưu" line
        self.assertEqual(style.issuer_for(TREE, "btm.cong_binh", CV, self.data).symbol, "TM-CôB")
        self.assertEqual(style.issuer_for(TREE, "btm.cong_binh", templates.get("BC"), self.data).symbol, "BC-TM")

    def test_a_new_draft_starts_with_that_header(self):
        draft = DraftContent.new(CV, style.issuer_for(TREE, "btm.khqs", CV, self.data), date(2026, 10, 26))
        self.assertEqual(draft.fields["co_quan_ban_hanh"]["text"], "BỘ THAM MƯU")
        self.assertEqual(draft.fields["co_quan_chu_quan"]["text"], "QUÂN KHU 3")
        self.assertEqual(draft.fields["so_ky_hieu"]["text"], "Số: …/TM-KHQS")
        self.assertEqual(draft.fields["noi_nhan"]["text"], "- Như trên;\n- Lưu: VT, KHQS. ….")
        unknown = DraftContent.new(CV, Issuer("Bộ Tham mưu", "Quân khu 3"), date(2026, 10, 26))
        self.assertEqual((unknown.fields["so_ky_hieu"]["text"], unknown.fields["noi_nhan"]["text"]),
                         ("Số: …/…-…", "- Như trên;\n- Lưu: VT, …. …."))
        self.assertEqual(unknown.fields["quyen_han"], {"text": "", "owner": "user"})

    def test_the_usual_signer_is_suggested_on_two_lines(self):
        draft = DraftContent.new(CV, style.issuer_for(TREE, "btm.khqs", CV, self.data), date(2026, 10, 26))
        self.assertEqual(draft.fields["quyen_han"], {"text": "KT. THAM MƯU TRƯỞNG\nPHÓ THAM MƯU TRƯỞNG", "owner": "assistant"})
        self.assertEqual(style.signer_lines("TL. THAM MƯU TRƯỞNG TRƯỞNG BAN CNTT"), "TL. THAM MƯU TRƯỞNG\nTRƯỞNG BAN CNTT")
        self.assertEqual(style.signer_lines("TM. BỘ TƯ LỆNH TƯ LỆNH"), "TM. BỘ TƯ LỆNH\nTƯ LỆNH")
        self.assertEqual(style.signer_lines("TRƯỞNG PHÒNG"), "TRƯỞNG PHÒNG")


class GuideTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = style_mining.build(corpus(), TREE)

    def test_a_unit_with_enough_documents_has_its_own_layout(self):
        g = style.guide(TREE, "btm.khqs", KH, self.data)
        self.assertEqual(g["based_on"], "5 kế hoạch của Phòng Khoa học quân sự")
        self.assertTrue(g["outline"][0].startswith("MỤC ĐÍCH, YÊU CẦU (100% văn bản): Mục đích; Yêu cầu"))
        self.assertTrue(any(c.startswith("Nhận được kế hoạch") for c in g["closings"]))
        self.assertEqual(g["header"]["so_ky_hieu"], "Số: …/KH-TM")
        self.assertEqual(g["signers"], [TTM])
        self.assertTrue(g["rules"]["general"] and g["rules"]["kind"])

    def test_a_unit_with_few_documents_takes_its_agencys_layout_but_names_only_its_own_correspondents(self):
        g = style.guide(TREE, "btm.cong_binh", KH, self.data)
        self.assertIn("của Bộ Tham mưu (Phòng Công binh có ít kế hoạch", g["based_on"])
        self.assertEqual(g["recipients"], ["Các tiểu đoàn công binh"])
        self.assertFalse(any("Nhận được kế hoạch" in c for c in g.get("closings", [])))  # Phòng KHQS's formula

    def test_without_profiles_the_general_rules_still_apply(self):
        g = style.guide(TREE, "btm.cong_binh", KH, {})
        self.assertIn("note", g)
        self.assertEqual(g["header"]["co_quan_ban_hanh"], "BỘ THAM MƯU")
        self.assertIn("bảo đảm", [w["use"] for w in g["rules"]["words"]])

    def test_profiles_are_read_from_the_data_folder(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(style, "profile_path", return_value=Path(folder) / "p.json"):
            self.assertEqual(style.profiles(), {})
            (Path(folder) / "p.json").write_text('{"version": %d, "units": {"btm": {}}}' % style_mining.VERSION, encoding="utf-8")
            self.assertEqual(style.profiles()["units"], {"btm": {}})


class SelectionStyleTest(unittest.TestCase):
    """The "Văn phong quân sự" button on a selected passage: the request itself carries the unit's style."""

    @classmethod
    def setUpClass(cls):
        cls.profiles = json.dumps(style_mining.build(corpus(), TREE))

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "profiles.json"
        path.write_text(self.profiles, encoding="utf-8")
        patch = mock.patch.object(style, "profile_path", return_value=path)
        patch.start()
        self.addCleanup(patch.stop)
        self.db = memory_session()
        self.user = User(username="u", password_hash="x", full_name="U", unit_id="btm.khqs", role="staff")
        self.db.add(self.user)
        self.db.flush()
        session = ChatSession(id="s1", user_id=self.user.id)
        self.db.add(session)
        self.db.flush()
        drafts.create(self.db, self.user, session, "KH")

    def prompt(self, action: str) -> str:
        context = {"block_id": "b1", "selection": "Đảm bảo an toàn.", "action": action}
        return chat.Turn("s1", self.user.id, 1, "t", "Sửa đoạn này.", [], True, context, False, None, None)._prompt(self.db)

    def test_military_style_is_given_with_the_request(self):
        text = self.prompt("military")
        self.assertIn("Văn phong cần theo (5 kế hoạch của Phòng Khoa học quân sự)", text)
        self.assertIn("Câu kết đơn vị hay dùng: Nhận được kế hoạch", text)
        self.assertIn("Dùng 'bảo đảm', không dùng 'đảm bảo'.", text)
        self.assertIn("không thêm thông tin mới", text)

    def test_other_actions_leave_it_to_the_assistant(self):
        text = self.prompt("rewrite")
        self.assertIn('đoạn b1 của bản dự thảo: "Đảm bảo an toàn."', text)
        self.assertNotIn("Văn phong cần theo", text)

    def test_a_chosen_preset_reaches_the_military_note_and_a_plain_edit(self):
        drafts.set_style(self.db, drafts.find(self.db, "s1"), {"preset": "lanh_dao", "detail": "ngan"})
        military = self.prompt("military")
        self.assertIn("Nêu kết quả và số liệu trước", military)
        self.assertIn("Viết ngắn:", military)
        rewrite = self.prompt("rewrite")
        self.assertIn("Người dùng chọn phong cách Báo cáo lãnh đạo, mức chi tiết Ngắn.", rewrite)
        self.assertNotIn("Văn phong cần theo", rewrite)


def reachable():
    try:
        QdrantClient(url=URL, api_key=KEY, timeout=3).get_collections()
        return True
    except Exception:
        return False


@unittest.skipUnless(reachable(), f"Qdrant không chạy ở {URL}")
class ExamplesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = QdrantClient(url=URL, api_key=KEY)
        cls.index = QdrantIndex(cls.client, HashEmbedder(128), f"test_{uuid.uuid4().hex[:10]}")
        cls.index.ensure_collection()
        cb, qb = Principal("btm.cong_binh", "staff"), Principal("btm.quan_bao", "staff")
        for doc_id, doc, placement in (
            ("bom", document(topic="rà phá bom mìn"), place_upload(TREE, cb)),
            ("song", document(topic="vượt sông"), place_upload(TREE, cb)),
            ("mat", document(topic="rà phá bom mìn bí mật"), place_upload(TREE, cb, declared_secret=True)),
            ("tb", document(topic="rà phá bom mìn trinh sát"), place_upload(TREE, qb)),
        ):
            cls.index.index_document(doc_id, doc, placement)

    @classmethod
    def tearDownClass(cls):
        cls.client.delete_collection(cls.index.collection)

    def test_examples_are_ordinary_documents_in_the_users_scope(self):
        scope = scope_for(TREE, Principal("btm.cong_binh", "commander"))  # may read secret documents, still gets none as examples
        found = style.examples(self.index, scope, KH, "rà phá bom mìn", limit=5)
        self.assertEqual(sorted(e["doc"].split(": ", 1)[1] for e in found), ["Công tác rà phá bom mìn", "Công tác vượt sông"])
        self.assertEqual(found[0]["outline"][0], "MỤC ĐÍCH, YÊU CẦU: Mục đích; Yêu cầu")
        self.assertTrue(found[0]["opening"].startswith("Thực hiện Kế hoạch số"))
        self.assertEqual(style.examples(self.index, scope, CV, "rà phá bom mìn"), [])  # no công văn


if __name__ == "__main__":
    unittest.main()
