"""The deterministic style check: facts a rewrite adds or drops, avoided words, and headings the unit usually has."""
import unittest

from app.drafting import style_check, templates
from app.drafting.content import DraftContent, Issuer


class FactsTest(unittest.TestCase):
    def test_numbers_dates_symbols_names_and_units(self):
        text = ("Hoàn thành 18/20 nhiệm vụ (15%) trước ngày 15/3/2026 theo Kế hoạch số 12/KH-QK3. "
                "Đồng chí Nguyễn Văn A của Phòng Khoa học quân sự báo cáo.")
        values = {fact.value for fact in style_check.facts(text)}
        self.assertTrue({"18/20", "15%", "15/3/2026", "12/KH-QK3", "Nguyễn Văn A"} <= values)
        self.assertIn("Phòng Khoa học quân sự", values)

    def test_a_title_after_dong_chi_is_not_a_personal_name(self):
        self.assertFalse(any(fact.kind == "name" for fact in style_check.facts("đồng chí Trưởng phòng chủ trì.")))

    def test_compare_warns_about_a_new_figure_and_notes_a_dropped_one(self):
        notes = style_check.compare("Hoàn thành 18/20 nhiệm vụ.", "Hoàn thành 15/20 nhiệm vụ ngày 02/01/2026.")
        self.assertTrue(any(note["message"] == "Có thêm '15/20' không có trong đoạn gốc." for note in notes))
        self.assertTrue(any(note["message"] == "Có thêm '02/01/2026' không có trong đoạn gốc." for note in notes))
        self.assertTrue(any(note["message"] == "Bỏ '18/20'." for note in notes))

    def test_a_year_kept_inside_a_date_is_not_reported_as_dropped(self):
        notes = style_check.compare("Năm 2026.", "Ngày 15/3/2026.")
        self.assertFalse(any(note["kind"] == "dropped" and note["where"] == "2026" for note in notes))


class WordingTest(unittest.TestCase):
    def test_an_avoided_word_and_a_stock_phrase(self):
        notes = style_check.wording("Đảm bảo đạt được nhiều kết quả tích cực.")
        self.assertTrue(any(note["message"] == "Dùng 'bảo đảm' thay cho 'đảm bảo'." for note in notes))
        self.assertTrue(any("đạt được nhiều kết quả tích cực" in note["message"] for note in notes))


class SectionsTest(unittest.TestCase):
    def test_a_usual_heading_the_draft_lacks_is_only_a_note(self):
        content = DraftContent.new(templates.get("KH"), Issuer("Bộ Tham mưu", "Quân khu 3"))
        content.set_content([{"kind": "heading", "text": "I. MỤC ĐÍCH, YÊU CẦU"}, {"kind": "para", "text": "Nội dung."}], "user")
        guide = {"outline": ["MỤC ĐÍCH, YÊU CẦU (100% văn bản)", "CÔNG TÁC BẢO ĐẢM (80% văn bản): Nội dung",
                             "PHỤ LỤC (20% văn bản)"]}
        notes = style_check.sections(content, guide)
        self.assertEqual([note["where"] for note in notes], ["CÔNG TÁC BẢO ĐẢM"])
        self.assertIn("80% kế hoạch", notes[0]["message"])
        self.assertGreater(style_check.blanks(content), 0)  # a new draft still has '…' to fill in


if __name__ == "__main__":
    unittest.main()
