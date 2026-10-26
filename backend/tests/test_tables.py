"""Tables of a draft: ids that survive edits, figures worked out by code, edits by id proposed to the user, and the Word output."""
import copy
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest import mock

from docx import Document

from app.core.errors import ValidationFailed
from app.drafting import style, structure, tables, templates
from app.drafting.check import check_draft
from app.drafting.content import DraftContent, Issuer
from app.drafting.render import render
from app.models import ChatSession, User
from app.services import drafts

from support import memory_session

EQUIPMENT = {
    "columns": [{"label": "TT"}, {"label": "Tên trang bị"}, {"label": "ĐVT"},
                {"label": "Số lượng", "children": [{"label": "Hiện có"}, {"label": "Đề xuất"}]},
                {"label": "Đơn giá"}, {"label": "Thành tiền"}],
    "rows": [{"type": "group", "cells": ["I", "Trang thiết bị phần cứng"]},
             ["1", "Máy tính để bàn", "Bộ", "10", "5", "15.000.000"],
             ["2", "Máy in", "Chiếc", "2", "…", "4.500.000"],
             {"type": "group", "cells": ["II", "Vật tư"]},
             ["3", "Mực in", "Hộp", "-", "20", "350.000"],
             {"type": "total", "cells": ["", "Cộng"]}]}
# c1 TT, c2 Tên, c3 ĐVT, c4 Số lượng (c5 Hiện có, c6 Đề xuất), c7 Đơn giá, c8 Thành tiền; r1..r6 in order.
# The group heading c4 holds no cells: the cells are TT, Tên, ĐVT, Hiện có, Đề xuất (4), Đơn giá, Thành tiền (6).
PRICED = [{"op": "formula", "column": "c8", "formula": "c6 × c7"}, {"op": "total", "row": "r6", "columns": ["c6", "c8"]}]


def cells(spec, row_id):
    return next(row["cells"] for row in spec["rows"] if row["id"] == row_id)


def column_ids(spec):
    return [node["id"] for column in spec["columns"] for node in (column, *(column.get("children") or []))]


class FiguresTest(unittest.TestCase):
    def test_figures_are_read_and_written_the_vietnamese_way(self):
        read = tables.parse_number
        self.assertEqual(read("1.200"), Decimal(1200))  # a dot groups thousands
        self.assertEqual(read("1.234.567,5"), Decimal("1234567.5"))
        self.assertEqual(read("12,5%"), Decimal("12.5"))
        self.assertEqual(read("1.5"), Decimal("1.5"))  # not a thousands group: a decimal point
        self.assertEqual(read("-"), Decimal(0))  # a dash means none
        self.assertEqual(read("−3"), Decimal(-3))
        self.assertIsNone(read("1,234.5"))
        self.assertIsNone(read("5 bộ"))
        self.assertEqual(tables.format_number(Decimal("1234567.456")), "1.234.567,46")
        self.assertEqual(tables.format_number(Decimal("1200.10")), "1.200,1")
        self.assertEqual(tables.format_number(Decimal("-0.001")), "0")

    def test_figures_in_text_leave_dates_out(self):
        found = tables.figures_in("Tổng kinh phí 133.000.000 đồng, tăng 12,5% so với ngày 10/6/2026.")
        self.assertEqual(found, {Decimal(133000000), Decimal("12.5")})


class IdsTest(unittest.TestCase):
    def test_every_column_and_row_gets_an_id(self):
        spec = tables.normalize(EQUIPMENT)
        self.assertEqual(column_ids(spec), ["c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8"])
        self.assertEqual([row["id"] for row in spec["rows"]], ["r1", "r2", "r3", "r4", "r5", "r6"])
        self.assertEqual(spec["seq"], {"c": 8, "r": 6})

    def test_ids_stay_with_their_rows_and_columns_and_are_not_reused(self):
        spec = tables.normalize(EQUIPMENT)
        spec, notes = tables.apply(spec, [{"op": "insert_row", "after": "r1", "cells": ["1", "Màn hình", "Chiếc", "4", "4"]},
                                          {"op": "insert_column", "label": "Ghi chú", "after": "c8"},
                                          {"op": "delete_row", "row": "r6"}])
        self.assertEqual(notes, ["Thêm dòng r7.", "Thêm cột c9 ('Ghi chú').", "Xóa dòng r6."])
        self.assertEqual([row["id"] for row in spec["rows"]], ["r1", "r7", "r2", "r3", "r4", "r5"])
        self.assertEqual(cells(spec, "r2")[:2], ["1", "Máy tính để bàn"])  # r2 is still the same line
        spec, notes = tables.apply(spec, [{"op": "insert_row", "cells": ["4", "Bàn phím"]}])
        self.assertEqual(notes, ["Thêm dòng r8."])  # r6 was deleted, its id is not handed out again
        again = tables.normalize(copy.deepcopy(spec))  # what the canvas sends back keeps its ids
        self.assertEqual([row["id"] for row in again["rows"]], [row["id"] for row in spec["rows"]])

    def test_new_rows_from_the_canvas_get_fresh_ids_and_duplicates_are_renamed(self):
        spec = tables.normalize(EQUIPMENT)
        sent = copy.deepcopy(spec)
        sent["rows"].insert(1, {"type": "row", "cells": ["0", "Mới"]})
        sent["rows"].append({"id": "r2", "type": "row", "cells": ["9", "Chép dòng"]})
        out = tables.normalize(sent)
        self.assertEqual([row["id"] for row in out["rows"]], ["r1", "r7", "r2", "r3", "r4", "r5", "r6", "r8"])

    def test_a_table_saved_before_ids_gets_them_by_position_without_changing_the_stored_spec(self):
        legacy = {"columns": [{"label": "TT"}, {"label": "Nội dung"}], "rows": [{"type": "row", "cells": ["1", "A"]}]}
        stored = copy.deepcopy(legacy)
        out = tables.ensure_ids(stored)
        self.assertEqual(stored, legacy)
        self.assertEqual((column_ids(out), out["rows"][0]["id"], out["seq"]), (["c1", "c2"], "r1", {"c": 2, "r": 1}))
        self.assertEqual(tables.ensure_ids(stored), out)  # the same each time it is read
        self.assertIs(tables.ensure_ids(out), out)


class CalculationTest(unittest.TestCase):
    def setUp(self):
        self.spec, _ = tables.apply(tables.normalize(EQUIPMENT), PRICED)

    def test_formula_columns_and_totals_are_worked_out_and_a_gap_stays_a_gap(self):
        self.assertEqual(cells(self.spec, "r2")[6], "75.000.000")
        self.assertEqual(cells(self.spec, "r3")[6], "…")  # 4.500.000 × "…"
        self.assertEqual(cells(self.spec, "r6")[4], "…")  # the total of a column with a missing figure is not a partial sum
        spec, _ = tables.apply(self.spec, [{"op": "set", "row": "r3", "column": "c6", "value": "3"}])
        self.assertEqual(cells(spec, "r6")[4], "28")
        self.assertEqual(cells(spec, "r6")[6], "95.500.000")
        self.assertEqual(tables.blanks(spec), 0)

    def test_a_group_row_and_a_group_total_add_only_their_own_rows(self):
        spec, _ = tables.apply(self.spec, [{"op": "set", "row": "r3", "column": "c6", "value": "3"},
                                           {"op": "total", "row": "r1", "columns": ["c6"]},
                                           {"op": "insert_row", "type": "total", "cells": ["", "Cộng II"], "columns": ["c6"],
                                            "scope": "group"}])
        self.assertEqual(cells(spec, "r1")[4], "8")  # group I: 5 + 3
        self.assertEqual(cells(spec, "r7")[4], "20")  # group II only
        self.assertEqual(cells(spec, "r6")[4], "28")  # the grand total is not double counted

    def test_a_percentage_of_the_totals_is_not_a_sum_of_percentages(self):
        spec = tables.normalize({
            "columns": [{"id": "c1", "label": "Đơn vị"}, {"id": "c2", "label": "Kế hoạch"}, {"id": "c3", "label": "Thực hiện"},
                        {"id": "c4", "label": "Tỷ lệ (%)", "formula": "c3 / c2 * 100"}],
            "rows": [["A", "4", "3"], ["B", "6", "6"], {"type": "total", "cells": ["Cộng"], "sum": ["c2", "c3"]}]})
        self.assertEqual([row["cells"][3] for row in spec["rows"]], ["75", "100", "90"])

    def test_division_by_zero_and_text_leave_a_gap_and_are_reported(self):
        spec, _ = tables.apply(self.spec, [{"op": "formula", "column": "c8", "formula": "c7 / (c6 - c6)"},
                                           {"op": "set", "row": "r5", "column": "c7", "value": "theo giá thị trường"}])
        self.assertEqual(cells(spec, "r2")[6], "…")
        self.assertNotIn("0%", cells(spec, "r2")[6])
        found = tables.problems(spec)
        self.assertIn("Dòng r2, cột 'Thành tiền': chia cho 0.", found)
        self.assertTrue(any("không phải số" in item for item in found))

    def test_formulas_that_cannot_be_worked_out_are_refused(self):
        for formula, words in (("c8 + 1", "chính cột đó"), ("c6 * c99", "không có"), ("c6 ** 2", "không hợp lệ"),
                               ("__import__('os')", "không hợp lệ"), ("c6 +", "không hợp lệ")):
            with self.assertRaises(ValidationFailed) as ctx:
                tables.apply(self.spec, [{"op": "formula", "column": "c8", "formula": formula}])
            self.assertIn(words, ctx.exception.message, formula)
        with self.assertRaises(ValidationFailed) as ctx:
            tables.apply(self.spec, [{"op": "formula", "column": "c7", "formula": "c8 / c6"}])
        self.assertIn("thành vòng", ctx.exception.message)


class EditTest(unittest.TestCase):
    def setUp(self):
        self.spec, _ = tables.apply(tables.normalize(EQUIPMENT), PRICED)

    def test_each_edit(self):
        spec, _ = tables.apply(self.spec, [
            {"op": "set", "row": "r4", "column": "c2", "value": "Vật tư tiêu hao"},
            {"op": "set_row", "row": "r5", "cells": ["3", "Mực in laser", "Hộp", "0", "24", "350.000"]},
            {"op": "rename_column", "column": "c7", "label": "Đơn giá (đồng)"},
            {"op": "insert_column", "label": "Nhu cầu", "parent": "c4", "values": {"r2": "15"}},
            {"op": "delete_column", "column": "c3"}])
        self.assertEqual(cells(spec, "r4")[1], "Vật tư tiêu hao")
        self.assertEqual([leaf["label"] for leaf in tables.leaves(spec)],
                         ["TT", "Tên trang bị", "Hiện có", "Đề xuất", "Nhu cầu", "Đơn giá (đồng)", "Thành tiền"])
        self.assertEqual(cells(spec, "r2"), ["1", "Máy tính để bàn", "10", "5", "15", "15.000.000", "75.000.000"])
        self.assertEqual(cells(spec, "r5")[-1], "8.400.000")  # 24 × 350.000, recomputed after set_row

    def test_deleting_a_group_column_takes_its_sub_columns_and_their_sums(self):
        spec, _ = tables.apply(self.spec, [{"op": "formula", "column": "c8", "formula": ""},
                                           {"op": "delete_column", "column": "c4"}])
        self.assertEqual(column_ids(spec), ["c1", "c2", "c3", "c7", "c8"])
        self.assertEqual(next(row for row in spec["rows"] if row["id"] == "r6")["sum"], ["c8"])
        self.assertEqual(len(cells(spec, "r2")), 5)

    def test_refused_edits_name_the_edit(self):
        cases = [([{"op": "set", "row": "r2", "column": "c8", "value": "1"}], "tính tự động"),
                 ([{"op": "delete_column", "column": "c6"}], "đang được dùng trong công thức"),
                 ([{"op": "delete_row", "row": "r99"}], "không có dòng 'r99'"),
                 ([{"op": "set", "row": "r2", "column": "c4", "value": "1"}], "có cột con"),
                 ([{"op": "explode"}], "không có"),
                 ([], "Chưa có thao tác")]
        for ops, words in cases:
            with self.assertRaises(ValidationFailed) as ctx:
                tables.apply(self.spec, ops)
            self.assertIn(words, ctx.exception.message, ops)
        with self.assertRaises(ValidationFailed) as ctx:
            tables.apply(self.spec, [{"op": "set", "row": "r2", "column": "c2", "value": "x"}, {"op": "delete_row", "row": "r0"}])
        self.assertTrue(ctx.exception.message.startswith("Thao tác 2 (delete_row)"))


def draft_with_table() -> DraftContent:
    draft = DraftContent.new(templates.get("CV"), Issuer("Ban CNTT", "Bộ Tham mưu", luu="CNTT"), date(2026, 10, 26))
    draft.set_fields({"trich_yeu": "đề xuất bổ sung trang thiết bị", "kinh_gui": "Thủ trưởng Bộ Tham mưu",
                      "noi_nhan": "- Như trên;\n- Lưu: VT, CNTT. A01."}, "assistant")
    draft.set_fields({"quyen_han": "TRƯỞNG BAN", "nguoi_ky": "Đại tá Nguyễn Văn A",
                      "dia_danh_ngay": "Hải Phòng, ngày 26 tháng 10 năm 2026"}, "user")
    draft.set_content([{"kind": "para", "text": "Ban CNTT đề xuất bổ sung 5 bộ máy tính, tổng kinh phí 75.000.000 đồng, chi tiết tại "
                                                "Phụ lục kèm theo."},
                       {"kind": "appendix", "text": "Danh mục trang thiết bị đề xuất bổ sung"},
                       {"kind": "table", "table": tables.apply(tables.normalize(EQUIPMENT), PRICED)[0]}])
    return draft


class ProposalTest(unittest.TestCase):
    def setUp(self):
        self.draft = draft_with_table()
        self.table = next(b for b in self.draft.blocks if b["kind"] == "table")

    def test_edits_become_one_proposal_and_the_table_stays_until_accepted(self):
        before = copy.deepcopy(self.table["table"])
        self.draft.edit_table(self.table["id"], 1, [{"op": "set", "row": "r3", "column": "c6", "value": "3"}], "Bổ sung số máy in")
        block, notes = self.draft.edit_table(self.table["id"], 1, [{"op": "insert_row", "after": "r3", "cells": ["3", "Máy quét"]}],
                                             "thêm máy quét")
        self.assertEqual(notes, ["Thêm dòng r7."])
        proposed = block["proposal"]["table"]
        self.assertEqual((cells(proposed, "r3")[4], cells(proposed, "r7")[1]), ("3", "Máy quét"))  # both edits
        self.assertEqual(block["proposal"]["note"], "Bổ sung số máy in; thêm máy quét")
        self.assertEqual(self.table["table"], before)
        self.draft.accept(self.table["id"])
        # the new row has no "Đề xuất" figure yet, so the total waits for it rather than leaving it out
        self.assertEqual((self.table["version"], cells(self.table["table"], "r6")[4]), (2, "…"))
        with self.assertRaises(ValidationFailed) as ctx:  # read at version 1, the table is at version 2 now
            self.draft.edit_table(self.table["id"], 1, [{"op": "set", "row": "r2", "column": "c6", "value": "6"}])
        self.assertIn("canvas_read", ctx.exception.message)

    def test_an_edit_that_changes_nothing_is_refused(self):
        with self.assertRaises(ValidationFailed):
            self.draft.edit_table(self.table["id"], 1, [{"op": "set", "row": "r2", "column": "c6", "value": "5"}])

    def test_a_passage_quoting_a_figure_the_table_dropped_is_marked_until_reviewed(self):
        para = self.draft.blocks[0]
        self.draft.edit_table(self.table["id"], 1, [{"op": "set", "row": "r2", "column": "c6", "value": "6"}])
        self.draft.accept(self.table["id"])
        self.assertEqual(para["stale"], {"tables": [self.table["id"]], "figures": ["75.000.000"]})  # "5 bộ" is one digit: left out
        self.assertTrue(any("75.000.000" in item["message"] for item in structure.check(self.draft)))
        self.draft.user_edit(reviewed=[para["id"]])
        self.assertNotIn("stale", para)

    def test_the_users_own_cell_edit_bumps_the_version_and_marks_passages(self):
        spec = copy.deepcopy(self.table["table"])
        spec["rows"][1]["cells"][4] = "6"
        self.draft.user_edit(blocks=[{"id": self.table["id"], "table": spec}])
        self.assertEqual((self.table["version"], self.table["owner"]), (2, "user"))
        self.assertIn("stale", self.draft.blocks[0])
        block, _ = self.draft.edit_table(self.table["id"], 2, [{"op": "set", "row": "r3", "column": "c6", "value": "1"}])
        self.assertEqual(block["proposal"]["action"], "replace")  # the assistant still proposes on the user's table

    def test_a_stored_block_without_version_or_ids_still_loads(self):
        stored = [{"id": "b1", "kind": "table", "text": "Bảng: TT | Nội dung (1 dòng)", "owner": "assistant", "proposal": None,
                   "table": {"columns": [{"label": "TT"}, {"label": "Nội dung"}], "rows": [{"type": "row", "cells": ["1", "A"]}]}}]
        draft = DraftContent.load(templates.get("CV"), self.draft.fields, stored, 1)
        block = draft.blocks[0]
        self.assertEqual((block["version"], block["table"]["rows"][0]["id"]), (1, "r1"))
        self.assertNotIn("id", stored[0]["table"]["rows"][0])
        draft.edit_table("b1", 1, [{"op": "set", "row": "r1", "column": "c2", "value": "B"}])

    def test_the_view_tells_the_page_and_the_gaps(self):
        shown = {b["id"]: b for b in self.draft.view()["blocks"]}
        table = shown[self.table["id"]]
        self.assertEqual((table["landscape"], table["too_wide"], table["blanks"], table["problems"]), (False, False, 4, []))  # r3 and the total: Đề xuất and Thành tiền


class RenderTest(unittest.TestCase):
    def test_the_word_file_prints_the_computed_table(self):
        draft = draft_with_table()
        table = next(b for b in draft.blocks if b["kind"] == "table")
        draft.edit_table(table["id"], 1, [{"op": "set", "row": "r3", "column": "c6", "value": "3"}])
        draft.accept(table["id"])
        with tempfile.TemporaryDirectory() as folder:
            path = render(draft, Path(folder) / "cv.docx", issuer_name="Ban CNTT")
            grid = Document(str(path)).tables[-1]
            texts = [[cell.text for cell in row.cells] for row in grid.rows]
        self.assertEqual(texts[0][3], "Số lượng")  # the group heading spans its sub-columns
        self.assertEqual(texts[1][3:5], ["Hiện có", "Đề xuất"])
        self.assertEqual(texts[-1][4], "28")
        self.assertEqual(texts[-1][6], "95.500.000")
        self.assertEqual(check_draft(draft)["counts"]["error"], 0)


class ServiceTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patch = mock.patch.object(style, "profile_path", return_value=Path(folder.name) / "profiles.json")
        patch.start()
        self.addCleanup(patch.stop)
        self.db = memory_session()
        self.user = User(username="u", password_hash="x", full_name="U", unit_id="btm.tac_chien", role="staff")
        self.db.add(self.user)
        self.db.flush()
        self.session = ChatSession(id="s1", user_id=self.user.id)
        self.db.add(self.session)
        self.db.flush()

    def test_a_table_proposal_is_stored_with_its_checks_and_decided_by_the_user(self):
        row = drafts.create(self.db, self.user, self.session, "CV")
        ids = drafts.set_content(self.db, row, [{"kind": "table", "table": EQUIPMENT}])
        block, notes = drafts.edit_table(self.db, row, ids[0], 1, PRICED, "tính thành tiền")
        checks = block["proposal"]["checks"]
        self.assertTrue(any(item["kind"] == "blanks" for item in checks))
        shown = next(b for b in drafts.view(row)["blocks"] if b["id"] == ids[0])
        self.assertEqual((shown["proposal"]["table"]["rows"][1]["cells"][6], shown["version"]), ("75.000.000", 1))
        drafts.decide(self.db, row, ids[0], accept=True)
        shown = next(b for b in drafts.view(row)["blocks"] if b["id"] == ids[0])
        self.assertEqual((shown["version"], shown["table"]["rows"][1]["cells"][6]), (2, "75.000.000"))
        self.assertGreaterEqual(drafts.check(self.db, row)["style"]["blanks"], 3)


if __name__ == "__main__":
    unittest.main()
