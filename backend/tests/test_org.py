import tempfile
import unittest
from pathlib import Path

from app.org import Unit, UnitTree

class UnitTreeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = UnitTree.load()

    def test_subtree_is_the_permission_scope(self):
        t = self.tree
        self.assertTrue(t.can_view("btm", "btm.cong_binh"))
        self.assertTrue(t.can_view("btm.cong_binh", "btm.cong_binh"))
        self.assertFalse(t.can_view("btm.cong_binh", "btm.quan_bao"))  # a phòng does not see its sibling
        self.assertFalse(t.can_view("btm.cong_binh", "btm"))  # nor its parent agency
        self.assertFalse(t.can_view("hckt", "btm.cong_binh"))
        self.assertEqual(t.subtree("btl"), frozenset(t.units))  # the root (Quân khu 3) sees everything

    def test_ancestors(self):
        self.assertEqual(self.tree.ancestors("btm.cong_binh"), ["btm", "btl"])
        self.assertEqual(self.tree.ancestors("btl"), [])

    def test_path_to_unit(self):
        r = self.tree.resolve_path
        self.assertEqual(r(["Bộ Tham mưu", "Phòng Công Binh", "HUẤN LUYỆN 2026"]).unit_id, "btm.cong_binh")
        self.assertEqual(r(["Cục HCKT", "Phòng Quan nhu tai lieu AI"]).unit_id, "hckt.quan_nhu")
        self.assertEqual(r(["CCT", "Cung cap Tai lieu thu nghiem AI", "Phòng CTQC"]).unit_id, "cct.ctqc")
        self.assertEqual(r(["Bộ Tham mưu", "Phòng QHNT"]).unit_id, "btm.qhnt")
        self.assertEqual(r(["Bộ Tham mưu", "d97", "năm 2023"]).unit_id, "btm.d97")
        self.assertEqual(r(["Bộ Tham mưu", "Phòng Hoá học"]).unit_id, "btm.hoa_hoc")  # tone placement variant
        self.assertEqual(r(["Bộ Tham mưu", "Thư mục lạ"]).unit_id, "btm")  # unknown folder: the nearest known unit
        self.assertIsNone(r(["Thư mục lạ"]).unit_id)

    def test_same_name_in_two_agencies_follows_the_parent_folder(self):
        self.assertEqual(self.tree.resolve_path(["Bộ Tham mưu", "Phòng Chính trị"]).unit_id, "btm.chinh_tri")
        self.assertEqual(self.tree.resolve_path(["Cục HCKT", "Phòng Chính trị"]).unit_id, "hckt.chinh_tri")

    def test_secret_folder_is_flagged(self):
        m = self.tree.resolve_path(["Bộ Tham mưu", "Phòng CY", "văn bản mật"])
        self.assertEqual((m.unit_id, m.secret_folder), ("btm.co_yeu", True))
        self.assertFalse(self.tree.resolve_path(["Bộ Tham mưu", "Phòng CY", "Văn bản thông thường"]).secret_folder)

    def test_header_agency(self):
        h = self.tree.resolve_header
        self.assertEqual(h("QUÂN KHU 3", "BỘ THAM MƯU").unit_id, "btm")
        self.assertEqual(h("", "BỘ THAM MƯU QUÂN KHU 3").unit_id, "btm")
        self.assertEqual(h("", "CỤC HẬU CẦN-KỸ THUẬT").unit_id, "hckt")  # missing spaces around the dash
        self.assertEqual(h("", "QUÂN KHU 3 PHÒNG THI HÀNH ÁN").unit_id, "btm.thi_hanh_an")  # longest name wins
        self.assertEqual(h("BỘ QUỐC PHÒNG", "QUÂN KHU 3").unit_id, "btl")

    def test_ambiguous_header_lists_candidates_instead_of_guessing(self):
        h = self.tree.resolve_header("", "PHÒNG CHÍNH TRỊ")
        self.assertIsNone(h.unit_id)
        self.assertEqual(sorted(h.candidates), ["btm.chinh_tri", "hckt.chinh_tri"])

    def test_unknown_header_agency(self):
        h = self.tree.resolve_header("", "TRẠM 2")
        self.assertEqual((h.unit_id, h.candidates), (None, []))

    def test_directory_file_is_consistent(self):
        ids = list(self.tree.units)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(any(u.provisional for u in self.tree.units.values()))  # units not on the chart are marked

    def test_rejects_a_dangling_parent_and_duplicate_ids(self):
        with self.assertRaises(ValueError):
            UnitTree([Unit("a", "A", "phong", parent="missing")])
        with self.assertRaises(ValueError):
            UnitTree([Unit("a", "A", "phong"), Unit("a", "B", "phong")])

if __name__ == "__main__":
    unittest.main()
