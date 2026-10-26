import unittest

from app.org import Principal, UnitTree, place, place_upload, scope_for

class AccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = UnitTree.load()

    def can(self, unit, role, folder, classification=""):
        p = place(self.tree, folder, classification)
        return scope_for(self.tree, Principal(unit, role)).allows(p.unit_id, p.level)

    def test_unit_scope(self):
        folder = ["Bộ Tham mưu", "Phòng Công Binh"]
        self.assertTrue(self.can("btm.cong_binh", "staff", folder))
        self.assertTrue(self.can("btm", "staff", folder))  # the parent agency sees its phòng
        self.assertTrue(self.can("btl", "staff", folder))
        self.assertFalse(self.can("btm.quan_bao", "staff", folder))  # a sibling does not
        self.assertFalse(self.can("hckt", "staff", folder))

    def test_secret_folder_is_for_commanders_only(self):
        folder = ["Bộ Tham mưu", "Phòng CY", "văn bản mật"]
        self.assertTrue(self.can("btm.co_yeu", "commander", folder))
        self.assertFalse(self.can("btm.co_yeu", "staff", folder))
        self.assertFalse(self.can("btm.co_yeu", "reviewer", folder))
        self.assertFalse(self.can("btm.co_yeu", "admin", folder))  # least privilege: admin manages, does not read
        self.assertFalse(self.can("btm.quan_bao", "commander", folder))  # a commander is still bound by the unit scope

    def test_secrecy_stamp_in_a_normal_folder_makes_it_secret(self):
        folder = ["Bộ Tham mưu", "Phòng Phòng không", "2023"]
        self.assertTrue(self.can("btm.phong_khong", "staff", folder))
        self.assertFalse(self.can("btm.phong_khong", "staff", folder, classification="mat"))
        self.assertTrue(self.can("btm.phong_khong", "commander", folder, classification="toi_mat"))

    def test_unknown_unit_fails_closed(self):
        p = place(self.tree, ["Thư mục lạ"])
        self.assertEqual(p.unit_id, "btl")
        self.assertIn("không xác định được đơn vị", p.reasons)
        self.assertFalse(self.can("btm", "commander", ["Thư mục lạ"]))
        self.assertTrue(self.can("btl", "commander", ["Thư mục lạ"]))

    def test_unknown_role_gets_ordinary_only(self):
        self.assertFalse(self.can("btm.co_yeu", "intern", ["Bộ Tham mưu", "Phòng CY", "văn bản mật"]))
        self.assertTrue(self.can("btm.co_yeu", "intern", ["Bộ Tham mưu", "Phòng CY"]))

    def test_unit_path_is_what_the_index_filters_on(self):
        p = place(self.tree, ["Bộ Tham mưu", "Phòng Công Binh"])
        self.assertEqual(p.unit_path, ("btl", "btm", "btm.cong_binh"))
        # "may read" is the same as "my unit is in the document's path": one match, no unit list
        for unit, expected in [("btm.cong_binh", True), ("btm", True), ("btl", True), ("btm.quan_bao", False), ("hckt", False)]:
            self.assertEqual(unit in p.unit_path, self.can(unit, "staff", ["Bộ Tham mưu", "Phòng Công Binh"]), unit)
            self.assertEqual(unit in p.unit_path, expected, unit)

    def test_upload_belongs_to_the_uploaders_unit(self):
        who = Principal("btm.cong_binh", "staff")
        p = place_upload(self.tree, who)
        self.assertEqual((p.unit_id, p.level, p.unit_path), ("btm.cong_binh", "thuong", ("btl", "btm", "btm.cong_binh")))
        self.assertEqual(place_upload(self.tree, who, classification="mat").level, "mat")
        self.assertEqual(place_upload(self.tree, who, declared_secret=True).level, "mat")
        self.assertFalse(scope_for(self.tree, who).allows(*(lambda x: (x.unit_id, x.level))(place_upload(self.tree, who, "mat"))))

    def test_reasons_are_recorded(self):
        p = place(self.tree, ["Bộ Tham mưu", "Phòng CY", "văn bản mật"], "mat")
        self.assertEqual(p.level, "mat")
        self.assertEqual(len(p.reasons), 2)

if __name__ == "__main__":
    unittest.main()
