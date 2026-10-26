"""Issuing body, trích yếu, number/date and signer of the opening and closing blocks (TT68 Phụ lục I ô 2, 3, 4, 5, 7)."""
import unittest

from app.parsing.header import extract_footer, extract_header, fill_from_images, find_footer
from app.parsing.models import Metadata
from app.parsing.reader import Line


def lines_of(*texts: str, align: str = "left") -> list[Line]:
    return [Line(i, t, align=align, empty=not t.strip()) for i, t in enumerate(texts)]


class OpeningBlockTest(unittest.TestCase):
    def test_issuing_body_stops_before_number_and_subject_of_a_two_column_pdf(self):
        lines = lines_of("QUÂN KHU 3", "BỘ THAM MƯU", "Số: /TM-CNTT", "V/v đóng góp ý kiến đối với dự thảo", "Quyết định của Thủ tướng Chính phủ",
                         "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", "Độc lập - Tự do - Hạnh phúc", "Hải Phòng, ngày   tháng   năm 2026",
                         "Kính gửi: Cục Doanh trại.", "Căn cứ Kế hoạch số 1.")
        meta = Metadata()
        extract_header(lines, meta)
        self.assertEqual((meta.parent_agency, meta.issuing_agency), ("QUÂN KHU 3", "BỘ THAM MƯU"))
        self.assertEqual(meta.subject, "V/v đóng góp ý kiến đối với dự thảo Quyết định của Thủ tướng Chính phủ")
        self.assertEqual(meta.symbol, "TM-CNTT")

    def test_number_and_date_on_one_line(self):
        lines = lines_of("QUÂN KHU 3", "BỘ TƯ LỆNH", "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", "Độc lập - Tự do - Hạnh phúc",
                         "Số: 470/QĐ-QK3 Hải Phòng, ngày 26 tháng 3 năm 2025", "QUYẾT ĐỊNH", "Về việc ban hành quy chế", "Căn cứ Luật.")
        lines[5].align = lines[6].align = "center"
        meta = Metadata()
        extract_header(lines, meta)
        self.assertEqual((meta.number, meta.symbol, meta.date), ("470", "QĐ-QK3", "2025-03-26"))
        self.assertEqual(meta.subject, "Về việc ban hành quy chế")


class NumberTest(unittest.TestCase):
    def test_blank_number_keeps_the_symbol_and_a_lone_slash_is_nothing(self):
        for text, expected in (("Số: /TM-CNTT", ("", "TM-CNTT")), ("Số: /", ("", "")), ("Số: 22/HD-TM", ("22", "HD-TM"))):
            meta = Metadata()
            extract_header(lines_of("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", text, "Căn cứ Luật."), meta)
            self.assertEqual((meta.number, meta.symbol), expected, text)


class DraftDateTest(unittest.TestCase):
    def test_blank_day_keeps_what_is_printed(self):
        meta = Metadata()
        extract_header(lines_of("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", "Số: /TM-CNTT Hải Phòng, ngày    tháng 01 năm 2026", "Kính gửi: Bộ Tư lệnh 86."), meta)
        self.assertEqual((meta.date, meta.date_partial, meta.number, meta.symbol), ("", "2026-01", "", "TM-CNTT"))

    def test_a_draft_is_tagged_and_knows_its_year(self):
        from app.services import tagging
        tags = tagging.auto_tags(title="Công văn", issued_date="2026-01", head="", scanned=False, draft=True)
        self.assertEqual(tags, ["Năm 2026", "Bản nháp"])


class SignerTest(unittest.TestCase):
    def signer(self, *texts: str) -> Metadata:
        meta = Metadata()
        extract_footer(lines_of("Nơi nhận:", "- Như trên;", *texts), meta)
        return meta

    def test_authority_line_is_not_the_title_and_rank_is_split_from_the_name(self):
        meta = self.signer("KT. THAM MƯU TRƯỞNG", "PHÓ THAM MƯU TRƯỞNG", "Đại tá Nguyễn Ngọc Yên")
        self.assertEqual(meta.signer, "Phó Tham mưu trưởng, Đại tá, Nguyễn Ngọc Yên")
        self.assertEqual((meta.signer_rank, meta.signer_name), ("Đại tá", "Đại tá Nguyễn Ngọc Yên"))

    def test_delegated_signature_keeps_abbreviations(self):
        meta = self.signer("TL. CHỦ NHIỆM", "TRƯỞNG PHÒNG XM-VT", "Đại tá Nguyễn Văn Ban")
        self.assertEqual(meta.signer, "Trưởng phòng XM-VT, Đại tá, Nguyễn Văn Ban")

    def test_pt_abbreviation_and_long_lines(self):
        self.assertEqual(self.signer("PT. CHỦ NHIỆM", "Đại tá Nguyễn Đức Huy").signer, "Phó Chủ nhiệm, Đại tá, Nguyễn Đức Huy")

    def test_title_without_a_name_is_not_taken_for_the_name(self):
        meta = self.signer("KT. TƯ LỆNH", "PHÓ TƯ LỆNH")
        self.assertEqual((meta.signer, meta.signer_name), ("Phó Tư lệnh", ""))

    def test_table_text_is_not_a_signer(self):
        meta = self.signer("Tổng số tiền truy lĩnh (60 tháng) của thương tật", "THƯƠNG TẬT")
        self.assertEqual(meta.signer, "")


class ImageFieldsTest(unittest.TestCase):
    def test_empty_fields_are_filled_from_the_text_read_off_the_stamps(self):
        meta = Metadata(symbol="QĐ-QK3", signer_role="TƯ LỆNH")
        found = fill_from_images(meta, ["QUÂN KHU 3", "Số: 1006/QĐ-QK3", "Hải Phòng, ngày 26 tháng 6 năm 2026"],
                                 ["Nơi nhận:", "- Lưu: VT.", "TƯ LỆNH", "Trung tướng Lương Văn Kiểm"])
        self.assertEqual((meta.number, meta.symbol, meta.date), ("1006", "QĐ-QK3", "2026-06-26"))
        self.assertEqual(meta.signer, "Tư lệnh, Trung tướng, Lương Văn Kiểm")
        self.assertEqual(set(found), {"số", "ngày", "người ký"})

    def test_ocr_misreading_a_tone_still_finds_the_rank_and_joined_lines_are_split(self):
        meta = Metadata()
        fill_from_images(meta, [], ["Nơi nhận:", "- Lưu: VT.", "KT. THAM MƯU TRƯỞNG PHÓ THAM MƯU TRƯỞNG", "Thiệu tướng Phạm Hoàng Long"])
        self.assertEqual(meta.signer, "Phó Tham mưu trưởng, Thiếu tướng, Phạm Hoàng Long")

    def test_existing_values_are_kept_and_the_digital_stamp_date_is_a_fallback(self):
        meta = Metadata(number="12", symbol="KH-TM")
        fill_from_images(meta, ["Số: 99/KH-TM"], ["Ký bởi: Bộ Tham mưu", "Ngày ký: 05/03/2026 10:11:12"])
        self.assertEqual((meta.number, meta.date), ("12", "2026-03-05"))


if __name__ == "__main__":
    unittest.main()
