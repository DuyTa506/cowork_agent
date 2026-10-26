# API Kiểm tra thể thức (`/api/format-check`)

Màn riêng, không lưu kho: tệp tải lên nằm trong thư mục tạm riêng của người dùng, không lập chỉ mục, chỉ chủ phiên xem được
(kể cả quản trị viên cũng không), tự xóa khi hết hạn (`retention_hours`, mặc định 24 giờ). Muốn đưa vào kho phải bấm *Lưu vào kho*.

| Phương thức | Đường dẫn | Việc |
|---|---|---|
| GET | `/options` | `{profiles:[{id,label,experimental}], default_profile, default_spell, accept, max_mb, retention_hours}` |
| POST | `/` | multipart: `file` (.docx .doc .pdf), `profile?`, `spell?` → `CheckOut` (201) |
| GET | `/{id}` | kết quả gần nhất |
| POST | `/{id}/recheck` | `{profile?, spell?}` kiểm tra lại bản gốc (bỏ bản đã sửa cũ) |
| POST | `/{id}/fix` | `{ids:[...], mode:"track"\|"apply"}` → `{applied, failed:[{id,reason}], after:{format,spelling}}` |
| GET | `/{id}/file` · `/fixed` · `/report` · `/annotated` | tải: tệp gốc · bản đã sửa (.docx) · báo cáo văn bản · bản có ghi chú Word |
| POST | `/{id}/save` | `{which:"fixed"\|"original", declared_secret?}` → `DocumentOut` (đưa vào kho, xử lý như tải lên) |
| DELETE | `/{id}` | xóa ngay |

Lỗi 422 (tệp không đọc được, bản scan PDF không có lớp chữ, id mục sửa không có), 404 (không có / hết hạn / không phải của bạn).

## `CheckOut`

`{id, name, size, kind ("word"|"pdf"), can_fix, profile, spell, fixed, counts:{format,spelling}, created_at, expires_at, result}`.
`expires_at` là ISO UTC có múi giờ (đếm ngược "còn 23 giờ 41 phút").

`result` (từ doccheck, văn bản người dùng đã là tiếng Việt):

- `facts.doc_type` — loại văn bản nhận dạng được (`QĐ`, `CV`, ...), `facts.origin` (`detected`|...).
- `counts` — `{format, spelling, items, manual}`; `tiers` — `{cao:"Cao", trungbinh:"Trung bình", thap:"Thấp"}`.
- `banner[]` — lỗi thể thức không gắn vào đoạn nào: `{severity ("error"|"warning"|"info"), rule, message, actual}`.
- `paras[]` — các đoạn để vẽ bản xem trước: `{pi, where ("body"|"cell"|"textbox"), table, row, col, text, label, blank, bold, align, page, pg (trang ước tính), msgs:[lỗi thể thức của đoạn], marks:[[start,end,itemId|null,tier|null], ...]}`. `marks` là vị trí chính tả sai trong `text` (chỉ số ký tự).
- `items[]` — mục có thể tự sửa, chọn bằng `id` (gửi vào `/fix`): `{id, kind ("format"|"layout"|"pagenum"|"spelling"), prop, label, before, after, explain, basis (căn cứ pháp lý), tier ("cao"|"trungbinh"|"thap"), group, pi, requires (id phải chọn cùng), locked (luôn áp), rules, ...}`; chính tả thêm `found, raw_after, ctx:[trước, sau], start, end`.
  Mặc định tick sẵn tier `cao` và `trungbinh`; `thap` không tick.
- `manual[]` — lỗi phải sửa tay: `{id, rule, pis, severity, message, reason, found, suggestion}`.
- `kind`, `kind_label`, `can_fix`, `note` (PDF: "không sửa trực tiếp được"), `profile:{id,label,experimental}`.

Mức độ trong màn: bắt buộc = `severity:"error"`, cảnh báo = `"warning"`, chính tả = mục `kind:"spelling"`; "tự sửa được" = số `items`.
