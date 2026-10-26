"""A PDF whose seal, number and date were stamped on by another system must not be reported as lacking them."""
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from app.services.formatcheck import engine


def finding(rule_id: str):
    return SimpleNamespace(rule_id=rule_id, severity="info", message="")


class StampedPdfTest(unittest.TestCase):
    def result(self):
        return SimpleNamespace(findings=[finding("INFO.so_chua_cap"), finding("MX.M06.8_dau_chu_ky_so.presence"),
                                         finding("QC.D10.1g.chu_ky_so_nguoi_ky.presence"), finding("PL1.II.line.5a_trich_yeu.length")])

    def test_absence_findings_go_and_the_others_stay(self):
        result = self.result()
        with mock.patch("app.ocr.render.stamp_pages", return_value=[0, 1]), mock.patch("app.parsing.parse_file", side_effect=engine.ValidationFailed("x")):
            note = engine._drop_false_absences(Path("x.pdf"), result)
        self.assertEqual([f.rule_id for f in result.findings], ["PL1.II.line.5a_trich_yeu.length"])
        self.assertIn("chèn từ hệ thống khác", note)

    def test_a_pdf_without_stamps_keeps_every_finding(self):
        result = self.result()
        with mock.patch("app.ocr.render.stamp_pages", return_value=[]):
            self.assertEqual(engine._drop_false_absences(Path("x.pdf"), result), "")
        self.assertEqual(len(result.findings), 4)


if __name__ == "__main__":
    unittest.main()
