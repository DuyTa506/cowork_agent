from __future__ import annotations
import re
from datetime import date

from .models import Metadata
from .reader import Line
from .textutil import fold, is_upper

# Tên loại văn bản in hoa giữa trang (TT68 ô 5a) và ký hiệu viết tắt trong số/ký hiệu (ô 3).
TYPE_NAMES = {
    "QUYET DINH": "Quyết định", "KE HOACH": "Kế hoạch", "BAO CAO": "Báo cáo", "TO TRINH": "Tờ trình",
    "THONG BAO": "Thông báo", "HUONG DAN": "Hướng dẫn", "CHI THI": "Chỉ thị", "NGHI QUYET": "Nghị quyết",
    "BIEN BAN": "Biên bản", "QUY CHE": "Quy chế", "QUY DINH": "Quy định", "MENH LENH": "Mệnh lệnh",
    "CHUONG TRINH": "Chương trình", "DE AN": "Đề án", "PHUONG AN": "Phương án", "GIAY MOI": "Giấy mời",
    "GIAY GIOI THIEU": "Giấy giới thiệu", "THONG TU": "Thông tư", "KET LUAN": "Kết luận", "NOI QUY": "Nội quy",
    "DANH SACH": "Danh sách", "THONG TRI": "Thông tri", "LENH": "Lệnh", "CONG DIEN": "Công điện",
}
TYPE_CODES = {
    "QD": "Quyết định", "KH": "Kế hoạch", "BC": "Báo cáo", "TTR": "Tờ trình", "TB": "Thông báo",
    "HD": "Hướng dẫn", "CT": "Chỉ thị", "NQ": "Nghị quyết", "BB": "Biên bản", "QC": "Quy chế",
    "QYD": "Quy định", "ML": "Mệnh lệnh", "CTR": "Chương trình", "DA": "Đề án", "PA": "Phương án",
    "GM": "Giấy mời", "GGT": "Giấy giới thiệu", "TT": "Thông tư", "KL": "Kết luận", "CV": "Công văn",
}
_ROLE_START = ("TU LENH", "CHU NHIEM", "THU TRUONG", "CHI HUY", "BO TRUONG", "GIAM DOC", "TONG THAM MUU",
               "CHINH UY", "CHINH TRI VIEN", "CHU TICH", "TRUONG PHONG", "TRUONG BAN", "CHI HUY TRUONG")
_QUOC_HIEU = re.compile(r"CONG HOA XA HOI CHU NGHIA VIET NAM")
_TIEU_NGU = re.compile(r"^DOC LAP\s*-?\s*TU DO\s*-?\s*HANH PHUC")
_SO = re.compile(r"^S[ốôo]\s*(?::|：|(?=[\d/]))\s*(.*)$", re.IGNORECASE)
_SO_SPLIT = re.compile(r"^(?P<num>[\w.]*?)\s*/\s*(?P<sym>.+)$")
_DATE = re.compile(r"(?P<place>[^,\d]{0,30}),?\s*ng[aà]y\s*(?P<d>\d{0,2})\s*th[aá]ng\s*(?P<m>\d{0,2})\s*n[aă]m\s*(?P<y>\d{4})", re.IGNORECASE)
_VV = re.compile(r"^(V/v|Về việc|V\.v)\b[\s:.]*(.*)$", re.IGNORECASE)
_KINH_GUI = re.compile(r"^Kính gửi\s*:?\s*(.*)$", re.IGNORECASE)
_BODY_START = re.compile(r"^(Căn cứ|Theo đề nghị|Điều 1\b)", re.IGNORECASE)
_NOI_NHAN = re.compile(r"^N[ơo]i nh[aậ]n\s*:?", re.IGNORECASE)
_BULLET = re.compile(r"^[-–—+•*]\s*")
_SIGN_NOISE = re.compile(r"^\(?\s*(đã ký|ký số|đã được ký|signed)\s*\)?$", re.IGNORECASE)
_TL = re.compile(r"^(TL|KT|TM|Q|TUQ)\.\s*", re.IGNORECASE)

def _clean_item(text: str) -> str:
    return _BULLET.sub("", text).strip().rstrip(";,.").strip()

def extract_header(lines: list[Line], meta: Metadata) -> int:
    """Fills `meta` from the opening block and returns the index in `lines` where the body starts."""
    limit = next((i for i, l in enumerate(lines) if not l.empty and _BODY_START.match(l.text)), min(len(lines), 60))
    limit = min(limit, 60)
    qh = next((i for i in range(limit) if _QUOC_HIEU.search(fold(lines[i].text))), None)
    cursor = 0

    # cơ quan ban hành (TT68 ô 2): tên cơ quan chủ quản và cơ quan ban hành viết HOA, đứng trên số/ký hiệu và trích yếu; text của PDF hai cột
    # thường đưa cả cột trái (cơ quan, số, V/v ...) lên trước quốc hiệu, nên dừng ở dòng "Số:" / "V/v" / dòng không viết hoa
    left_title: list[str] = []
    if qh is not None:
        agency: list[str] = []
        left = [l.text for l in lines[:qh] if not l.empty and not re.fullmatch(r"[-_–— ]+", l.text)]
        stop = len(left)
        for k, t in enumerate(left):
            if _SO.match(t) or _VV.match(t) or not is_upper(t) or _DATE.match(t):
                stop = k
                break
            agency.append(t)
        for t in left[stop:]:  # trích yếu của công văn đứng ngay dưới số/ký hiệu, có thể xuống dòng
            if _SO.match(t) or _KINH_GUI.match(t):
                continue
            if _VV.match(t) or left_title:
                left_title.append(t)
        if len(agency) >= 2:
            meta.parent_agency, meta.issuing_agency = agency[0], " ".join(agency[1:])
        elif agency:
            meta.issuing_agency = agency[0]
        cursor = qh + 1

    for i in range(limit):
        l = lines[i]
        if l.empty:
            continue
        text = l.text
        if not meta.symbol and not meta.number:
            m = _SO.match(text)
            if m:
                value, dated = _split_date(m.group(1))  # a two-column PDF line: "Số: 470/QĐ-QK3 Hải Phòng, ngày 26 tháng 3 năm 2025"
                _parse_so(value, meta)
                cursor = max(cursor, i + 1)
                if not dated:
                    continue
                text = dated
        if not meta.date_text:
            d = _DATE.match(text) if len(text) < 80 else None
            if d:
                meta.place = d.group("place").strip(" ,")
                meta.date_text = text
                if d.group("d") and d.group("m"):
                    try:
                        meta.date = date(int(d.group("y")), int(d.group("m")), int(d.group("d"))).isoformat()
                    except ValueError:
                        pass
                elif d.group("m") and 1 <= int(d.group("m")) <= 12:
                    meta.date_partial = f"{d.group('y')}-{int(d.group('m')):02d}"
                else:
                    meta.date_partial = d.group("y")
                cursor = max(cursor, i + 1)

    # tên loại văn bản + trích yếu
    start = cursor
    type_idx = next((i for i in range(start, limit) if not lines[i].empty and fold(lines[i].text).rstrip(" :") in TYPE_NAMES
                     and lines[i].align == "center"), None)
    if type_idx is not None:
        meta.doc_type = TYPE_NAMES[fold(lines[type_idx].text).rstrip(" :")]
        title: list[str] = []
        j = type_idx + 1
        while j < len(lines) and j < type_idx + 8:
            l = lines[j]
            if l.empty:
                j += 1
                continue
            if l.align != "center" or _BODY_START.match(l.text) or _KINH_GUI.match(l.text):
                break
            if l.table is not None and lines[type_idx].table is None:  # ô tiêu đề của bảng nội dung, không phải trích yếu
                break
            f = fold(l.text)
            if any(f.startswith(r) for r in _ROLE_START) and is_upper(l.text):
                break
            title.append(l.text)
            j += 1
        meta.title = " ".join(title)
        meta.subject = meta.title
        cursor = j
    else:
        for i in range(start, limit):
            m = _VV.match(lines[i].text) if not lines[i].empty else None
            if m:
                meta.title = (m.group(2) or lines[i].text).strip()
                meta.subject, cursor = _subject_lines(lines, i, limit)
                cursor = max(cursor, i + 1)
                break

    # kính gửi
    for i in range(cursor, min(len(lines), cursor + 12)):
        m = _KINH_GUI.match(lines[i].text) if not lines[i].empty else None
        if not m:
            continue
        if m.group(1):
            meta.recipients_to.append(_clean_item(m.group(1)))
        k = i + 1
        while k < len(lines) and (lines[k].empty or _BULLET.match(lines[k].text)):
            if not lines[k].empty:
                meta.recipients_to.append(_clean_item(lines[k].text))
            k += 1
        cursor = k
        break
    if not meta.title and left_title:
        m = _VV.match(left_title[0])
        meta.title = " ".join([(m.group(2) if m and m.group(2) else left_title[0] if not m else "")] + left_title[1:]).strip()
        meta.subject = " ".join(left_title)
    if not meta.title:
        for i in range(max(start - 1, 0), min(len(lines), cursor + 3)):
            m = _VV.match(lines[i].text) if not lines[i].empty else None
            if m:
                meta.title = (m.group(2) or lines[i].text).strip()
                meta.subject = _subject_lines(lines, i, len(lines))[0]
                break

    # phân loại: tên in giữa trang > ký hiệu viết tắt > có "Kính gửi"/"V/v" thì là công văn
    if not meta.doc_type:
        meta.doc_type = TYPE_CODES.get(fold(meta.doc_type_code), "")
    if not meta.doc_type and (meta.recipients_to or any(_VV.match(l.text) for l in lines[:limit] if not l.empty)):
        meta.doc_type = "Công văn"
    return cursor

_DATE_TAIL = re.compile(r"\s*(?<![\w-])(?P<date>[A-ZÀ-Ỹ][^,\d/-]{0,30},\s*ngày\s.*)$")

def _split_date(value: str) -> tuple[str, str]:
    """('470/QĐ-QK3', 'Hải Phòng, ngày 26 tháng 3 năm 2025') from a "Số:" line that also carries the date; ('value', '') when it does not."""
    m = _DATE_TAIL.search(value)
    return (value[:m.start()].strip(), m.group("date").strip()) if m else (value, "")

def _subject_lines(lines: list[Line], i: int, limit: int) -> tuple[str, int]:
    """The "V/v ..." line at `i` with the lines that wrap it (same paragraph look: centred or italic, not a new part of the heading)."""
    parts = [lines[i].text.strip()]
    j = i + 1
    while j < min(limit, len(lines), i + 6):
        l = lines[j]
        if l.empty or _KINH_GUI.match(l.text) or _BODY_START.match(l.text) or _SO.match(l.text) or _DATE.match(l.text) or l.align != lines[i].align:
            break
        parts.append(l.text.strip())
        j += 1
    return " ".join(parts), j

def _parse_so(value: str, meta: Metadata) -> None:
    value = value.strip()
    if not value.strip("/ "):  # "Số: /" left blank for the number to be stamped on
        return
    m = _SO_SPLIT.match(value)
    if m:
        meta.number, meta.symbol = m.group("num").strip(), m.group("sym").strip()
        head = fold(meta.symbol.split("-")[0].strip())
        if head in TYPE_CODES:
            meta.doc_type_code = meta.symbol.split("-")[0].strip()
    else:
        meta.number = value
    meta.is_draft = not meta.number

_ANNEX = re.compile(r"^(PHỤ LỤC|BIỂU|MẪU|DANH SÁCH|BẢNG|SƠ ĐỒ|TỔNG HỢP|ĐƠN VỊ TÍNH)\b", re.IGNORECASE)
_FOOTER_LINE_WORDS = 12  # a line longer than this after the signature is body text again (an annex), not a signature line

def find_footer(lines: list[Line], body_start: int) -> tuple[int, int]:
    """(start, end) of the 'Nơi nhận' + signature block; what follows `end` (phụ lục, biểu mẫu) is annex content.

    Returns (len, len) when the document has no such block."""
    idx = next((i for i in range(len(lines) - 1, body_start - 1, -1) if _NOI_NHAN.match(lines[i].text)), None)
    if idx is None:
        return len(lines), len(lines)
    # chữ ký không nằm trong bảng thường đứng ngay trước "Nơi nhận": ngắn, căn giữa/phải hoặc thụt sâu
    start = idx
    while start - 1 > body_start:
        prev = lines[start - 1]
        if prev.empty:
            start -= 1
            continue
        signature_like = prev.align in ("center", "right") or prev.ind_left_cm >= 6
        if signature_like and len(prev.text.split()) <= 10 and not prev.text.endswith((".", ";", ":")) or _TL.match(prev.text):
            start -= 1
            continue
        break
    end = idx + 1
    for i in range(idx + 1, len(lines)):
        l = lines[i]
        if l.empty:
            continue
        if _ANNEX.match(l.text):
            break
        if _BULLET.match(l.text) or len(l.text.split()) <= _FOOTER_LINE_WORDS:
            end = i + 1
            continue
        break
    return start, end

def extract_footer(lines: list[Line], meta: Metadata) -> list[str]:
    """Parses the footer lines into distribution list and signer; returns the footer's text lines."""
    texts = [l.text for l in lines if not l.empty]
    in_noi_nhan = False
    sign: list[str] = []
    for t in texts:
        if _NOI_NHAN.match(t):
            in_noi_nhan = True
            rest = _NOI_NHAN.sub("", t).strip()
            if rest and is_upper(rest):  # "Nơi nhận: ĐỘI TRƯỞNG": hai cột cùng một đoạn, phần sau là chức danh người ký
                sign.append(rest)
            elif rest:
                meta.distribution.append(_clean_item(rest))
            continue
        if in_noi_nhan and (_BULLET.match(t) or t.lower().startswith(("như trên", "lưu", "- lưu"))):
            meta.distribution.append(_clean_item(t))
        else:
            sign.append(t)
    # a lone letter is a stamp fragment; a long line or one with digits/brackets is a table cell or a sentence, not a title or a name
    sign = [s for s in sign if not _SIGN_NOISE.match(s) and len(s.strip()) > 1 and len(s.split()) <= 9 and not any(c.isdigit() or c in "()" for c in s.replace("QK3", ""))]
    set_signer(meta, sign)
    return texts

_RANKS = ("Binh nhì", "Binh nhất", "Hạ sĩ", "Trung sĩ", "Thượng sĩ", "Thiếu úy", "Trung úy", "Thượng úy", "Đại úy", "Thiếu tá", "Trung tá",
          "Thượng tá", "Đại tá", "Thiếu tướng", "Trung tướng", "Thượng tướng", "Đại tướng")
_RANK_AT_START = re.compile(r"^(?P<rank>" + "|".join(r.replace("ú", "[úu]").replace("ý", "[ýy]") for r in _RANKS) + r")\b[\s,.:;-]*(?P<name>.*)$", re.IGNORECASE)
_RANK_NAME = re.compile(r"(?P<rank>" + "|".join(_RANKS) + r")\s+(?P<name>(?:[A-ZÀ-Ỹ][\wÀ-ỹ]*\s+){1,4}[A-ZÀ-Ỹ][\wÀ-ỹ]*)")  # inside OCR text, where lines are not reliable

def _case_word(w: str) -> str:
    """Lower-cases a word of an upper-case title but keeps abbreviations (no vowel, or with a digit/hyphen): 'XM-VT', 'CNTT', 'QK3'."""
    if any(c.isdigit() or c == "-" for c in w) or not any(c in "aeiouyàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ" for c in w.lower()):
        return w.upper()
    return w.lower()

def format_role(lines: list[str]) -> str:
    """'KT. THAM MƯU TRƯỞNG' + 'PHÓ THAM MƯU TRƯỞNG' -> 'Phó Tham mưu trưởng': the authority line is dropped, the title keeps its own words."""
    lines = [re.sub(r"^(?:(?:TM|TL|KT|TUQ|Q)\.?\s.*?)\s(?=PHÓ\s)", "", l) if _AUTHORITY.match(l) and " PHÓ " in l else l for l in lines]  # OCR joins "KT. TƯ LỆNH" and "PHÓ TƯ LỆNH"
    own = [l for l in lines if not _AUTHORITY.match(l)] or [_AUTHORITY.sub("", l) for l in lines]
    out = [_case_word(w) for w in re.sub(r"^PT\.\s*", "PHÓ ", " ".join(own), flags=re.IGNORECASE).split()]
    if not out:
        return ""
    out[0] = out[0][:1].upper() + out[0][1:]
    for i, w in enumerate(out[:-1]):
        if w.lower() == "phó":
            out[i + 1] = out[i + 1][:1].upper() + out[i + 1][1:]
    return " ".join(out)

def set_signer(meta: Metadata, sign: list[str]) -> None:
    """Splits the signature lines into title (upper case or an authority line), rank and name; keeps whatever was found."""
    role: list[str] = []
    person = ""
    for text in sign:
        t = text.strip()
        if _RANK_AT_START.match(t) or (not is_upper(t) and not _AUTHORITY.match(t) and not _TITLE_WORD.search(fold(t))):
            person = t
        else:
            role.append(t)
    m = _RANK_AT_START.match(person)
    words = (m.group("name") if m else person).split()
    if person and not (2 <= len(words) <= 6 and all(w[:1].isupper() for w in words)):  # a table cell or a sentence, not a person's name
        person, m = "", None
    role = [r for r in role if (_TITLE_WORD.search(fold(r)) or _AUTHORITY.match(r)) and len(r.split()) <= 10]  # "THƯƠNG TẬT" in a form is not a title
    meta.signer_lines = role
    meta.signer_role = " ".join(role)
    meta.signer_name = person
    meta.signer_rank = m.group("rank").capitalize() if m else ""
    compose_signer(meta)

def compose_signer(meta: Metadata) -> None:
    """Fills `meta.signer` from the role, rank and name already on `meta`."""
    name = meta.signer_name
    if meta.signer_rank:
        name = _RANK_AT_START.sub(lambda m: m.group("name"), name).strip()
    role = format_role(meta.signer_lines or [meta.signer_role]) if (meta.signer_lines or meta.signer_role) else ""
    meta.signer = ", ".join(x for x in (role, meta.signer_rank, name) if x)

_AUTHORITY = re.compile(r"^(TM|TL|KT|TUQ|Q)\b\.?\s*", re.IGNORECASE)  # who signs for whom (TT68 phụ lục I, ô 7): "KT. TƯ LỆNH", also when the dot is lost
_TITLE_WORD = re.compile(r"\b(TRUONG|PHO|CHU NHIEM|GIAM DOC|TU LENH|CHINH UY|CHI HUY|BI THU|CHU TICH|VIEN TRUONG|TONG)\b")
_STAMP_DATE = re.compile(r"ng[aà]y\s*k[ýy]\s*:?\s*(?P<d>\d{1,2})[/-](?P<m>\d{1,2})[/-](?P<y>\d{4})", re.IGNORECASE)

_ADOPTED = ("parent_agency", "issuing_agency", "place", "date_text", "date", "number", "symbol", "doc_type", "doc_type_code", "title", "subject")

def _adopt_header(meta: Metadata, first: list[str]) -> list[str]:
    """Runs the header parser over the OCR lines of the first page and copies the fields `meta` is still missing."""
    texts = [t.strip() for t in first[:60] if t.strip()]
    lines, after_type = [], False
    for i, t in enumerate(texts):
        centred = is_upper(t) or after_type
        after_type = fold(t).rstrip(" :") in TYPE_NAMES
        lines.append(Line(i, t, align="center" if centred else "left"))
    seen = Metadata()
    extract_header(lines, seen)
    names = {"number": "số", "date": "ngày"}
    found = []
    for name in _ADOPTED:
        if not getattr(meta, name) and getattr(seen, name):
            setattr(meta, name, getattr(seen, name))
            if name in names:
                found.append(names[name])
    return found

def _rank_name(text: str) -> str:
    """'Đại tá Nguyễn Ngọc Yên' from a line of OCR text, or '' ; the rank is matched without diacritics ('Thiệu tướng' is 'Thiếu tướng')."""
    folded = fold(text)
    if len(folded) != len(text):
        m = _RANK_NAME.search(text)
        return m.group(0) if m else ""
    for rank in _RANKS:
        at = re.search(r"\b" + re.escape(fold(rank)) + r"\b", folded, re.IGNORECASE)
        if not at:
            continue
        name = re.match(r"\s+((?:[A-ZÀ-Ỹ][\wÀ-ỹ]*\s+){1,4}[A-ZÀ-Ỹ][\wÀ-ỹ]*)", text[at.end():])
        if name:
            return f"{rank} {name.group(1)}"
    return ""

def fill_from_images(meta: Metadata, first: list[str], last: list[str]) -> list[str]:
    """Fills what the text layer missed from the text read off the seal/signature pictures (OCR lines of the first and last page).

    Only empty fields are filled. Returns the names of the fields that were found."""
    found: list[str] = []
    found += _adopt_header(meta, first)
    if not meta.number or not meta.date:
        for t in (l.strip() for l in first[:45]):
            m = _SO.match(t)
            if m:
                value, dated = _split_date(m.group(1))
                t = dated or value
            if m and not meta.number:
                keep_symbol = meta.symbol
                _parse_so(value, meta)
                if keep_symbol and not meta.symbol:
                    meta.symbol = keep_symbol
                if meta.number:
                    found.append("số")
            d = _DATE.match(t) if len(t) < 80 else None
            if d and not meta.date and d.group("d") and d.group("m"):
                try:
                    meta.date = date(int(d.group("y")), int(d.group("m")), int(d.group("d"))).isoformat()
                    meta.date_text, meta.place = t, d.group("place").strip(" ,") or meta.place
                    found.append("ngày")
                except ValueError:
                    pass
    if not meta.date:  # the digital-signature stamp: "Ngày ký: 12/09/2026"
        for t in first + last:
            m = _STAMP_DATE.search(t)
            if m:
                try:
                    meta.date = date(int(m.group("y")), int(m.group("m")), int(m.group("d"))).isoformat()
                    found.append("ngày")
                    break
                except ValueError:
                    continue
    if not meta.signer_name:
        tail = [t.strip() for t in last if t.strip()]
        for i in reversed(range(len(tail))):  # the last one: earlier mentions of a rank and a name are in the body
            t = tail[i]
            m = _rank_name(t)
            if not m:
                continue
            roles: list[str] = []
            for prev in reversed(tail[max(0, i - 4):i]):  # the title sits right above the name
                if (is_upper(prev) or _TL.match(prev)) and not _NOI_NHAN.match(prev) and len(prev) > 1:
                    roles.insert(0, prev)
                else:
                    break
            set_signer(meta, (meta.signer_lines or ([meta.signer_role] if meta.signer_role else roles)) + [m])
            found.append("người ký")
            break
    return found

_SECRECY = {"MAT": "mat", "TOI MAT": "toi_mat", "TUYET MAT": "tuyet_mat"}
_SECRECY_LINE = re.compile(r"^[\(\[\s]*(TUYET MAT|TOI MAT|MAT)[\)\]\s.]*$")  # the stamp: a line that is only "MẬT"
_SECRECY_FIELD = re.compile(r"\bDO MAT\s*[:\-]\s*(TUYET MAT|TOI MAT|MAT)\b")  # "Độ mật: Mật" (a blank "Độ mật: ……" does not match)
_SECRECY_TELEGRAM = re.compile(r"^DIEN (TUYET MAT|TOI MAT|MAT)\b")  # "ĐIỆN MẬT ĐI"
_SECRECY_RANK = ("mat", "toi_mat", "tuyet_mat")

def detect_classification(lines: list[Line], scan: int = 30) -> str:
    """The secrecy stamp in the first `scan` non-empty lines ('' when none); the highest one wins."""
    best = -1
    seen = 0
    for l in lines:
        if l.empty:
            continue
        seen += 1
        if seen > scan:
            break
        f = fold(l.text)
        m = _SECRECY_LINE.match(f) or _SECRECY_FIELD.search(f) or _SECRECY_TELEGRAM.match(f)
        if m:
            best = max(best, _SECRECY_RANK.index(_SECRECY[m.group(1)]))
    return _SECRECY_RANK[best] if best >= 0 else ""
