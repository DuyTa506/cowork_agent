# API Trợ lý AI (`/api/chat`) và Canvas

Hợp đồng giữa giao diện và backend (backend đã hiện thực đúng tài liệu này; kiểm thử đầu-cuối ở `backend/tests/test_chat_api.py`).
Mọi đường dẫn cần `Authorization: Bearer`. Lỗi: JSON `{detail}` (422 dữ liệu sai, 404 không thấy hoặc không có quyền, 409 đang bận).

## Cuộc trò chuyện

| | | |
|---|---|---|
| GET | `/api/chat/sessions` | `[Session]` mới cập nhật trước |
| POST | `/api/chat/sessions` | `{title?}` → `Session` (201) |
| GET | `/api/chat/sessions/{id}` | `{session, messages:[Message], attachments:[Attachment], draft: Draft \| null}` |
| PATCH | `/api/chat/sessions/{id}` | `{title}` đổi tên → `Session` |
| DELETE | `/api/chat/sessions/{id}` | xóa cả tin nhắn, tệp đính kèm, bản dự thảo và nhật ký đề xuất (204) |
| POST | `/api/chat/sessions/{id}/messages` | gửi tin nhắn → **luồng SSE** (bên dưới) |
| POST | `/api/chat/sessions/{id}/stop` | dừng lượt đang trả lời (204) |
| POST | `/api/chat/sessions/{id}/warm` | khởi động trợ lý ở nền (202); gọi khi người dùng bấm vào ô soạn tin hoặc mở cuộc trò chuyện: lần trả lời đầu mất ~10 giây nếu chưa khởi động |

`Session = {id: string, title, created_at, updated_at}`. Tiêu đề tự đặt từ tin nhắn đầu (cắt ~48 ký tự).

`Message = {id: number, role: "user"|"assistant", content, steps:[Step], citations:[Citation], status: "done"|"error"|"stopped", attachment_ids:[number], created_at}`.
Với `assistant`, `content` đã được đánh số nguồn `[1]`, `[2]`... tương ứng `citations[].n`; khi `status` là `error`, `content` là thông báo lỗi.

`Step = {id: string, kind: "thinking"|"tool", title, summary, status: "running"|"done"|"error", duration_ms, tool (chuỗi, `""` với bước suy nghĩ), detail}`; mã phiên (`session_id`) và `doc_id` là chuỗi:
- `thinking`: title "Đã suy nghĩ 6 giây", summary = ý đầu của suy luận, `detail.text` = toàn văn suy luận.
- `tool`: `tool` ∈ `search_documents | list_documents | read_document | search_attachments | list_attachments | read_attachment | summarize_document | canvas_create | canvas_style | canvas_set_fields | canvas_set_content | canvas_edit_block | canvas_edit_table | canvas_read | canvas_check`;
  title tiếng Việt ("Tìm văn bản", "Đọc văn bản", "Tóm tắt văn bản", "Soạn nội dung"...), summary dạng
  `từ khóa · “tập huấn công binh” · 6 đoạn trong 3 văn bản · 0,4 giây`; `detail.arguments` (đối số gọi), `detail.result = {documents:[{doc_id,label,section}], count}`
  hoặc `{error}`. `doc_id` là chuỗi: của tệp đính kèm có dạng `att<N>`, của kho là mã văn bản (chuỗi, không phải số). Các `tool` song song xuất hiện cùng lúc (nhiều step `running`).

`Citation = {n, doc_id, kind: "store"|"attachment", title, ref, doc_type, date, unit_name, section, text, pi:[first,last], readable}`.
`ref` = "24/KH-PTM". `pi` là khoảng chỉ số đoạn nguồn để tô sáng trong `DocumentViewer`; `[-1,-1]` nếu không có. Mở nguồn:
`kind=store` → `GET /api/documents/{doc_id}/content`; `kind=attachment` → `GET /api/chat/sessions/{sid}/attachments/{aid}/content` (aid = số sau `att`).
`readable=false` khi người dùng không còn quyền xem (ẩn liên kết, không có `text`).

### Gửi tin nhắn

Body: `{text, attachment_ids?: [int], canvas?: bool, context?: {block_id?, selection?}}`. Trả lỗi thường (JSON, trước khi mở luồng) nếu
tin trống/quá dài (422), **tin bị kiểm duyệt đầu vào chặn (422, kèm `code:"moderation"`; tin không được gửi, lần chặn được ghi nhật ký)**, tệp đính kèm chưa `ready` hoặc không thuộc cuộc này (422), cuộc đang trả lời (409).
- `canvas: true` khi người dùng bật Canvas trong ô soạn (chip "Canvas ×" cạnh nút "+"); khi không bật mà yêu cầu rõ là soạn văn bản, agent cũng tự mở canvas.
- `context`: khi người dùng bôi đen đoạn trong canvas rồi chọn "Viết lại / Rút gọn / Văn phong quân sự / Chính tả": `block_id` của đoạn, `selection` là chữ được chọn, `action` là nút (`rewrite`, `shorten`, `military`, `spelling`); `text` là yêu cầu. Với `military`, máy chủ tự ghép hồ sơ văn phong của đơn vị và phong cách đang chọn vào yêu cầu, không phụ thuộc việc trợ lý có gọi `canvas_style` hay không. Agent trả lời bằng đề xuất (`proposal`) chứ không sửa thẳng. Nút "Áp dụng cho toàn văn" gửi `action: "restyle"` và không kèm `block_id`.
- `attachment_ids`: tệp đính kèm (đã `ready`) dùng cho lượt này. Không có cách tham chiếu văn bản trong kho: agent tự tìm trong kho theo quyền người hỏi.

Phản hồi `text/event-stream`; mỗi sự kiện có dòng `event: <type>` và `data: <json>`; dòng `: keep-alive` định kỳ (bỏ qua):

| event | data | ý nghĩa |
|---|---|---|
| `session` | `{session_id, user_message_id, title}` | mở đầu; `title` đã cập nhật nếu là tin đầu |
| `moderation` | `{level, action:"warn", categories, message, count}` | tin có lời lẽ vi phạm nhẹ nhưng vẫn được gửi: hiện `message` cho người dùng (đã ghi nhật ký `moderation.warn`); chỉ xuất hiện ngay sau `session` |
| `step` | `{step: Step}` | một dòng "việc đã làm"; **upsert theo `step.id`** (xuất hiện lúc `running`, cập nhật khi `done`/`error`) |
| `canvas` | `{draft: Draft}` | bản dự thảo vừa đổi (sau mỗi lệnh `canvas_*` trừ `canvas_read`, `canvas_style`; có thể chưa có `blocks`) |
| `answer` | `{text, citations:[Citation]}` | câu trả lời cuối, đã đánh số nguồn |
| `error` | `{message}` | lỗi (mô hình chưa cấu hình, hệ thống bận...) — luôn kèm `done` ngay sau |
| `done` | `{message_id, title, status}` | kết thúc (`status`: done/error/stopped); sau đó đóng luồng |

Đáp án đến **một lần** sau các step (runtime báo theo từng bước, không theo token): giao diện nên hiển thị dần (hiệu ứng gõ) khi nhận `answer`.
Lượt trả lời chạy tiếp ở máy chủ kể cả khi trình duyệt đóng; tải lại `GET /sessions/{id}` sẽ thấy kết quả (lúc đang chạy: chưa có tin trợ lý, gửi tiếp trả 409).
`stop` dừng lượt; tin trợ lý lưu với `status:"stopped"` (kèm các step đã làm, `content` rỗng).

## Tệp đính kèm (tải nhanh vào chat)

| | | |
|---|---|---|
| POST | `/api/chat/sessions/{id}/attachments` | multipart `file` (.docx .doc .pdf, tối đa 10 tệp/cuộc) → `Attachment` (201, `state:"queued"`) |
| GET | `/api/chat/sessions/{id}/attachments/{aid}` | `Attachment` — hỏi lại (poll 1–2 giây) tới khi `ready`/`failed` |
| DELETE | `/api/chat/sessions/{id}/attachments/{aid}` | 204 |
| GET | `.../attachments/{aid}/content` | `[Paragraph]` như `/api/documents/{id}/content` |
| GET | `.../attachments/{aid}/file` | tệp gốc |

`Attachment = {id, name, size, state: "queued"|"processing"|"ready"|"failed", detail, title, document_type, chunk_count}`.
Tệp chỉ dùng trong cuộc trò chuyện này (quyền xem gắn với cuộc trò chuyện), không vào kho văn bản.

## Canvas (bản dự thảo trong cuộc trò chuyện)

Mỗi cuộc trò chuyện có tối đa một bản dự thảo. Ô soạn có nút "+" mở menu: **Tải tệp lên · Canvas** (bật Canvas → chip "Canvas ×").
Mẫu lấy từ bảng yêu cầu của Thông tư 68/2023/TT-BQP (doccheck): Công văn, Kế hoạch, Báo cáo, Thông báo, Tờ trình, Hướng dẫn, Chương trình,
Phương án, Đề án, Dự án, Chỉ thị, Quyết định, Nghị quyết, Quy chế, Quy định, Công điện, Giấy mời.

| | | |
|---|---|---|
| GET | `/api/chat/sessions/{id}/draft` | `Draft` hoặc `null` |
| POST | `/api/chat/sessions/{id}/draft` | `{kind: "CV"\|"KH"\|…, replace?: bool}` mở bản trống → `Draft` (201); 409 nếu đã có và không `replace` |
| PATCH | `/api/chat/sessions/{id}/draft` | người dùng sửa tay: `{fields?: {key: text}, blocks?: [{id, text?, table?}], insert?: {after: id\|null, kind, text, table?}, delete?: [id], style?: {preset, detail}, unit_id?: string, reviewed?: [id]}` → `Draft` (422 nếu khóa không có). `table` là spec cả bảng (server tự tính cột công thức và dòng cộng). `reviewed` bỏ nhãn “số liệu bảng đã đổi” trên các đoạn đó. `style` là phong cách và mức chi tiết; giá trị lạ bị đưa về mặc định (`don_vi`, `vua`) |
| POST | `/api/chat/sessions/{id}/draft/blocks/{block_id}/accept` | chấp nhận đề xuất của trợ lý → `Draft` |
| POST | `/api/chat/sessions/{id}/draft/blocks/{block_id}/reject` | từ chối → `Draft` |
| POST | `/api/chat/sessions/{id}/draft/check` | kiểm tra thể thức bản dựng DOCX bằng doccheck, kèm kiểm tra văn phong → `DraftCheck` |
| GET | `/api/chat/sessions/{id}/draft/export` | tải `.docx` (tên tệp = trích yếu) |
| POST | `/api/chat/sessions/{id}/draft/save` | `{declared_secret?: bool}` lưu vào Kho → `{document: DocumentOut}` (201) |
| DELETE | `/api/chat/sessions/{id}/draft` | bỏ bản dự thảo (204) |

```
Draft = {
  id: number, title, version, updated_at,
  template: {code: "M08", kind: "CV", name: "Công văn", doc_type: "CV", authority: "Thông tư 68/2023/TT-BQP"},
  fields: { <key>: Field },          // chỉ gồm các thành phần mẫu này có
  blocks: [Block],                   // phần nội dung theo thứ tự
  missing: [<field key>],            // ô bắt buộc mà còn trống hoặc còn "…"
  style: {preset: "don_vi"|"lanh_dao"|"chi_dao", detail: "ngan"|"vua"|"day_du"},
  style_options: {presets: [{id, name}], detail: [{id, name}]},  // nhãn trên Canvas, lấy từ style_rules.yaml
  history: [{version, at, by: "assistant"|"user", summary}],
  unit_id?: string, unit_name?: string   // đơn vị soạn (rỗng = đơn vị của người dùng)
}
Field = {label, text, owner: "system"|"assistant"|"user", needs_input: bool, multiline: bool}
Block = {id: "b1", kind: "heading"|"para"|"item"|"table"|"appendix", text, owner: "assistant"|"user",
         proposal: Proposal | null, version: number,
         table?: Table,                              // kind table
         label?: string, landscape?: bool,           // appendix: "Phụ lục II"; table/appendix: khổ in
         too_wide?: bool, blanks?: number, problems?: [string],  // table
         stale?: {tables: [id], figures: [string]}}  // đoạn văn trích số liệu bảng đã đổi
Proposal = {action: "replace"|"delete"|"insert", text, note, checks?: [StyleFinding], table?: Table, kind?}
Table = {columns: [Column], rows: [Row], seq: {c, r}, landscape?: bool}
Column = {id: "c1", label, align?: "left"|"center"|"right", formula?: "c6 * c7", children?: [Column]}
Row = {id: "r1", type: "row"|"group"|"section"|"total", cells: [string], sum?: [column id], scope?: "all"|"group"}
StyleFinding = {severity: "warning"|"info", kind, message, where}
DraftCheck = {counts:{error, warning, manual}, findings:[{severity: "error"|"warning", message, where, ref}], checked_at,
              style: {wording: [StyleFinding], sections: [StyleFinding], blanks: number}}
```

`owner` quyết định cách vẽ: `system` = gạch chấm, máy tự điền (người dùng vẫn bấm vào để đổi được, khi đó thành `user`);
`assistant` = nền nhạt; `user`/`needs_input` = gạch đứt, cần người dùng nhập. Trợ lý chỉ điền được ô trống/còn "…", không ghi đè ô `system` hay `user`,
và không viết đè lên đoạn `user` (chỉ đề xuất).
Khóa `fields` (theo thứ tự trên trang): `co_quan_chu_quan`, `co_quan_ban_hanh`, `so_ky_hieu` ("Số: …/CV-…", văn thư cấp số),
`quoc_hieu`, `tieu_ngu`, `dia_danh_ngay` ("……, ngày 26 tháng 10 năm 2026": địa danh cần người dùng điền), `ten_loai` ("BÁO CÁO", mẫu có tên loại),
`trich_yeu` (text **không** gồm "V/v "; công văn tự thêm "V/v" khi dựng văn bản), `kinh_gui` (text không gồm "Kính gửi:"), `can_cu`, `quyen_han`,
`nguoi_ky`, `noi_nhan` (mỗi dòng "- …", dòng cuối "- Lưu: VT, <đơn vị soạn>. <người soạn><số bản>.").
`Proposal.action`: `replace` → hiện diff giữa `block.text` và `proposal.text` (bảng: diff theo ô, ghép dòng/cột theo `id`); `delete` → đoạn bị gạch; `insert` → đoạn mới có `block.text` rỗng và nội dung ở `proposal.text` (bảng: `proposal.table`).
`Proposal.checks` (với `replace`): cảnh báo tất định, không chặn. Với đoạn văn: `Có thêm '…' không có trong đoạn gốc` khi đề xuất có số liệu, ngày, số ký hiệu, tên đơn vị hoặc tên người mà đoạn gốc không có; `Bỏ '…'` khi bỏ đi; `Dùng 'bảo đảm' thay cho 'đảm bảo'` và cụm sáo rỗng lấy từ `style_rules.yaml`. Với bảng: cảnh báo công thức/cộng không tính được, và thông tin `Còn n ô '…' chờ người dùng điền số liệu`. Trợ lý nhận chính danh sách này trong kết quả `canvas_edit_block` / `canvas_edit_table`.

Bảng (`kind: "table"`): số liệu chưa có để `"…"`; cột `formula` và dòng `total`/`group` có `sum` do server tính (không `eval`; chia 0 hoặc thiếu số liệu ra `"…"`). Số viết kiểu Việt (`1.200` = 1200, `12,5` = 12.5). Dòng/cột có `id` ổn định (`r3`, `c8`); mỗi khối có `version` riêng. Trợ lý sửa bảng bằng `canvas_edit_table(block_id, base_version, ops)` — một lệnh, nhiều thao tác (`set`, `set_row`, `insert_row`, `delete_row`, `insert_column`, `delete_column`, `rename_column`, `formula`, `total`); `base_version` lệch thì từ chối và bảo gọi `canvas_read`. Lỗi công cụ canvas ném `ToolError` nên mô hình đọc được lý do (không bị che thành "Error executing tool"). `canvas_edit_block` chỉ dùng cho đoạn văn; bảng dùng `canvas_edit_table`. Chấp nhận đề xuất bảng có thể gắn `stale` lên đoạn văn còn trích số liệu cũ (`stale.figures`); người dùng bấm “Đã xem” gửi PATCH `reviewed`. Phụ lục (`kind: "appendix"`) in từ trang mới sau phần ký; một bảng quá rộng tự kéo phụ lục sang khổ ngang.
Thanh Canvas có menu **Văn phong** (`don_vi` Chuẩn đơn vị, `lanh_dao` Báo cáo lãnh đạo, `chi_dao` Chỉ đạo cấp dưới) và mức **Ngắn / Vừa / Đầy đủ**. Đổi lựa chọn lưu bằng PATCH `style`; nếu đã có nội dung, thông báo có nút áp dụng cho toàn văn (trợ lý đề xuất sửa từng đoạn, không ghi đè). Phong cách không được bỏ thành phần bắt buộc của loại văn bản.
`DraftCheck.style`: `wording` trên toàn văn, `sections` là mục mà từ 60% văn bản cùng loại của đơn vị có mà bản thảo chưa có (chỉ là gợi ý), `blanks` là số chỗ còn dấu `…`.
`canvas_style(topic, kind, section)`: `section` là tên mục đang viết; mỗi văn bản mẫu khi đó có thêm `passage` (một hai câu đầu của mục đó, chỉ để học cách viết). Kết quả có `chosen` là phong cách đang chọn.
Có nút Chấp nhận / Từ chối cho mỗi đề xuất. Không có endpoint "sửa tự động" từng lỗi thể thức: người dùng sửa bằng PATCH hoặc nhờ trợ lý.
Mỗi lần chấp nhận, từ chối, hoặc sửa tay một đoạn do trợ lý viết được ghi vào `draft_revisions` (nội dung trước / đề xuất / bản cuối) để thống kê tỷ lệ chấp nhận và tỷ lệ phải sửa lại; xóa cuộc trò chuyện hoặc bỏ bản dự thảo thì xóa theo. Trang Thống kê chỉ hiện số đếm.

Cập nhật bản dự thảo đến theo hai đường: sự kiện SSE `canvas` trong lượt chat, và các lệnh `PATCH`/`accept`/`reject` của người dùng.
Mọi thay đổi tăng `version`.
