"""What each kind of document is made of.

The components of every model document of Thông tư 68/2023/TT-BQP (Mẫu 01–20) are in doccheck's curated requirement matrix. A
template here is a *kind of document* ("Công văn", "Báo cáo"...) bound to one of those models; its fields are the components the
model requires or allows, so a draft never offers a box the format does not have, and `doccheck` judges the result against the
same matrix it came from.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import doccheck

MATRIX_FILE = Path(doccheck.__file__).parent / "data" / "tt68_rules_curated.json"

# Fields in the order they appear on the page: key -> (label, matrix components that give it, multiline)
FIELD_ORDER: tuple[tuple[str, str, tuple[str, ...], bool], ...] = (
    ("co_quan_chu_quan", "Cơ quan chủ quản", ("2_ten_co_quan.chu_quan",), False),
    ("co_quan_ban_hanh", "Cơ quan, đơn vị ban hành", ("2_ten_co_quan.ban_hanh",), False),
    ("so_ky_hieu", "Số, ký hiệu", ("3_so_ky_hieu",), False),
    ("quoc_hieu", "Quốc hiệu", ("1_quoc_hieu_tieu_ngu",), False),
    ("tieu_ngu", "Tiêu ngữ", ("1_quoc_hieu_tieu_ngu",), False),
    ("dia_danh_ngay", "Địa danh, ngày tháng năm", ("4_dia_danh_thoi_gian",), False),
    ("ten_loai", "Tên loại văn bản", ("5a_ten_loai",), False),
    ("trich_yeu", "Trích yếu", ("5a_trich_yeu", "5b_trich_yeu_cong_van"), False),
    ("kinh_gui", "Kính gửi", ("9a_kinh_gui",), True),
    ("can_cu", "Căn cứ", ("6_can_cu",), True),
    ("quyen_han", "Quyền hạn, chức vụ người ký", ("7a_quyen_han_chuc_vu",), False),
    ("nguoi_ky", "Cấp bậc, họ và tên người ký", ("7b_ho_ten_nguoi_ky",), False),
    ("noi_nhan", "Nơi nhận", ("9b_noi_nhan", "9b_luu"), True),
)
PRESENT = ("required", "optional")  # matrix statuses that give the draft a box ("conditional" ones depend on secrecy/medium)


@dataclass(frozen=True)
class Template:
    """A kind of document the assistant can draft.

    Attributes:
        kind: Symbol of the kind as used in the document number (``CV``, ``KH``, ``BC``).
        name: Display name ("Công văn").
        model: Code of the TT68 model it follows (``M08``).
        title_word: The kind's name as printed above the trích yếu ("BÁO CÁO"); empty when the model has none (Công văn).
        fields: Keys of the fields the model has, in page order.
        required: Keys of the fields the model requires.
        has_can_cu: Whether the body opens with "Căn cứ" lines.
        decision_word: Line that introduces the operative part ("QUYẾT ĐỊNH:"), for the kinds that have one.
        guide: How the model lays out the body and the legal basis, in the circular's own words (shown to the assistant).
        pages: Pages of the circular showing the model (for the "Theo Thông tư 68" note).
    """

    kind: str
    name: str
    model: str
    title_word: str
    fields: tuple[str, ...]
    required: frozenset[str]
    has_can_cu: bool
    pages: tuple[int, ...]
    decision_word: str = ""
    guide: str = ""

    @property
    def code(self) -> str:
        """Identifier used in the API: the TT68 model code, plus the kind where one model serves several (``M06.BC``)."""
        return self.model if self.model not in SHARED_MODELS else f"{self.model}.{self.kind}"

    @property
    def authority(self) -> str:
        return "Thông tư 68/2023/TT-BQP"


# (kind, display name, model, title printed above trích yếu)
KINDS: tuple[tuple[str, str, str, str], ...] = (
    ("CV", "Công văn", "M08", ""),
    ("KH", "Kế hoạch", "M07", "KẾ HOẠCH"),
    ("BC", "Báo cáo", "M06", "BÁO CÁO"),
    ("TB", "Thông báo", "M06", "THÔNG BÁO"),
    ("TTr", "Tờ trình", "M06", "TỜ TRÌNH"),
    ("HD", "Hướng dẫn", "M06", "HƯỚNG DẪN"),
    ("CTr", "Chương trình", "M06", "CHƯƠNG TRÌNH"),
    ("PA", "Phương án", "M06", "PHƯƠNG ÁN"),
    ("ĐA", "Đề án", "M06", "ĐỀ ÁN"),
    ("DA", "Dự án", "M06", "DỰ ÁN"),
    ("CT", "Chỉ thị", "M06", "CHỈ THỊ"),
    ("QĐ", "Quyết định", "M02", "QUYẾT ĐỊNH"),
    ("NQ", "Nghị quyết", "M01", "NGHỊ QUYẾT"),
    ("QC", "Quy chế", "M05", "QUY CHẾ"),
    ("QyĐ", "Quy định", "M05", "QUY ĐỊNH"),
    ("CĐ", "Công điện", "M09", "CÔNG ĐIỆN"),
    ("GM", "Giấy mời", "M10", "GIẤY MỜI"),
)
DECISION_WORD = {"M01": "QUYẾT NGHỊ:", "M02": "QUYẾT ĐỊNH:"}
SHARED_MODELS = frozenset(model for model in {k[2] for k in KINDS} if sum(1 for k in KINDS if k[2] == model) > 1)


@lru_cache(maxsize=1)
def _matrix() -> dict[str, dict[str, Any]]:
    """TT68 requirement matrix by model code."""
    data = json.loads(MATRIX_FILE.read_text(encoding="utf-8"))
    return {row["template"]: row for row in data["requirement_matrix"]}


def _guide(row: dict[str, Any]) -> str:
    """What the model prescribes for the legal basis and the body, from the matrix evidence."""
    parts = []
    for key, label in (("6_can_cu", "Căn cứ"), ("6_noi_dung", "Nội dung"), ("9b_luu", "Dòng Lưu")):
        spec = row["components"].get(key, {})
        if spec.get("status") in PRESENT and spec.get("evidence"):
            parts.append(f"{label}: {spec['evidence']}")
    return "\n".join(parts)


@lru_cache(maxsize=1)
def all_templates() -> dict[str, Template]:
    """Every draftable kind, by `Template.code`."""
    out: dict[str, Template] = {}
    for kind, name, model, title in KINDS:
        row = _matrix()[model]
        status = {key: spec["status"] for key, spec in row["components"].items()}
        fields, required = [], set()
        for key, _label, components, _multi in FIELD_ORDER:
            states = [status.get(c, "absent") for c in components]
            if key in ("ten_loai",) and not title:
                continue
            if key == "noi_nhan" and not ("required" in states or "optional" in states):
                continue
            if any(s in PRESENT for s in states):
                fields.append(key)
                if "required" in states:
                    required.add(key)
        template = Template(kind, name, model, title, tuple(fields), frozenset(required), status.get("6_can_cu") in PRESENT,
                            tuple(row.get("pages", ())), DECISION_WORD.get(model, ""), _guide(row))
        out[template.code] = template
    return out


def get(code: str) -> Template:
    """The template with `code` (also accepts a bare kind symbol like ``CV``); `KeyError` when there is none."""
    templates = all_templates()
    if code in templates:
        return templates[code]
    for template in templates.values():
        if template.kind.lower() == code.lower():
            return template
    raise KeyError(code)


def label_of(key: str) -> str:
    """Display label of a field key."""
    return next(label for k, label, _c, _m in FIELD_ORDER if k == key)


def is_multiline(key: str) -> bool:
    """Whether a field holds several lines."""
    return next(m for k, _l, _c, m in FIELD_ORDER if k == key)
