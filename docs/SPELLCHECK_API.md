# API Kiểm tra chính tả (`/api/spellcheck`)

Màn riêng, cùng cơ chế tạm với Kiểm tra thể thức: văn bản dán hoặc tệp tải lên nằm trong thư mục tạm riêng của người dùng
(`TEMP_DIR/check/<id>/`), không lập chỉ mục, không vào kho văn bản, chỉ chủ phiên xem được (kể cả quản trị viên cũng không), tự xóa khi hết hạn
(`doccheck.temp_retention_hours`, mặc định 24 giờ) hoặc khi người dùng rời màn. Phiên chính tả và phiên thể thức là hai loại riêng
(`check_sessions.purpose`): id của màn này không mở được ở `/api/format-check` và ngược lại.

| Phương thức | Đường dẫn | Việc |
|---|---|---|
| GET | `/options` | `{accept, max_mb, max_chars, retention_hours}` |
| POST | `/` | multipart: `file` (.docx .doc .pdf .txt .md .markdown), `markdown?` → `SpellOut` (201) |
| POST | `/text` | `{text, markdown?}` văn bản dán (tối đa 200.000 ký tự, xuống dòng `\n` hoặc `\r\n`) → `SpellOut` (201) |
| GET | `/{id}` | kết quả hiện tại (đã trừ danh sách bỏ qua) |
| PUT | `/{id}/ignore` | `{words:[...]}` thay toàn bộ danh sách từ bỏ qua của phiên; trả `SpellOut` không còn các từ đó |
| POST | `/{id}/fix` | `{ids:[...], mode:"track"\|"apply"}` → `{applied, failed:[{id,reason}], after:{spelling}, text?}` |
| GET | `/{id}/file` · `/fixed` · `/report` | tải: tệp gốc · bản đã sửa (`<tên>_sua.docx`, hoặc `<tên>_sua<.txt\|.md>` với văn bản) · báo cáo văn bản |
| DELETE | `/{id}` | xóa ngay |

Lỗi 422: tệp không đọc được, bản scan PDF không có lớp chữ, văn bản rỗng hoặc quá dài, tệp `.txt` có byte 0, id mục sửa không còn, PDF đòi sửa.
404: không có / hết hạn / không phải của bạn. Mỗi lần soát và mỗi lần sửa ghi nhật ký (`spellcheck.run`, `spellcheck.fix`; nội dung văn bản không vào nhật ký).

## `SpellOut`

`{id, name, size, kind ("word"|"pdf"|"text"), can_fix (false với PDF), fixed, counts:{spelling}, ignore:[từ bỏ qua], created_at, expires_at, result}`.
Văn bản dán có `name: "van_ban.txt"`.

`result` có hình dạng như `result` của Kiểm tra thể thức nhưng chỉ còn chính tả (`banner` rỗng, `paras[].msgs` rỗng, `counts.format` = 0):

- `paras[]` — `{pi, text, marks:[[start,end,itemId|null,tier|null],...], page?, pg?, ...}`. Văn bản: mỗi dòng là một đoạn, `start/end` tính theo dòng bằng đơn vị UTF-16 (như chỉ số chuỗi JavaScript).
- `items[]` — chỗ sửa chọn được: `{id ("S:<pi>:<start>:<end>"), kind:"spelling", prop (syllable|tone_style|spacing|punctuation|encoding|lm_real_word|lm_non_word|extra_word), label (tên loại lỗi tiếng Việt), found, raw_after, before, after, ctx:[trước, sau], start, end, tier ("cao"|"trungbinh"|"thap"), explain, layer, group}`. `before`/`after` là dạng nhìn thấy được (dấu cách thành `␣`); `found`/`raw_after` là chuỗi nguyên văn.
- `manual[]` — lỗi chưa có gợi ý chắc chắn, người dùng tự xem lại: `{id ("M:spl:..."), rule ("SPELL.*"), pis, message, reason, found, suggestion, label, ctx}`.
- `counts` — `{format:0, spelling: items+manual, items, manual}`; `ignored` — số mục đã ẩn nhờ danh sách bỏ qua; `tiers`; `kind`, `kind_label`, `can_fix`, `note` (PDF: vì sao không sửa được), `chars`.
- Văn bản: `file:{enc, eol}` cách ghi lại tệp (UTF-8, UTF-8 có BOM, UTF-16; kiểu xuống dòng của đầu vào); tệp không phải Unicode đọc theo Windows-1258 và lưu lại UTF-8.

## Danh sách bỏ qua

`PUT /{id}/ignore` lưu danh sách trong phiên. So khớp theo từ nguyên văn không phân biệt hoa thường; mọi chỗ có từ đó (mục tự sửa lẫn ghi chú) và dấu gạch sóng của chúng biến mất khỏi kết quả, `ignored` báo số mục đã ẩn. Gửi `words: []` để báo lại tất cả. Tối đa 500 từ, mỗi từ tối đa 80 ký tự. Danh sách mất cùng phiên.
Các mục bỏ qua cũng không có trong báo cáo, không tính vào `after.spelling` sau khi sửa.

## Sửa

- **Word**: dựng lại từ tệp gốc mỗi lần, chỉ áp đúng các `ids` (Track Changes nếu `mode: "track"`, sửa thẳng nếu `"apply"`); `after.spelling` là kết quả soát lại bản đã sửa.
- **Văn bản** (dán, .txt, .md): sửa ở máy chủ trên văn bản đã lưu, trả `text` (đã sửa, giữ kiểu xuống dòng); `/fixed` tải về cùng bảng mã và đuôi tệp.
- **PDF**: không sửa được (`can_fix: false`, `/fix` trả 422); dùng `/report`.
