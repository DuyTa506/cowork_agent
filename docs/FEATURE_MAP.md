# Ma trận tính năng 0.2.0

Trạng thái: **Có** = đã làm và có kiểm thử; **Kế hoạch** = đã chốt thiết kế, chưa làm; **Chưa có** = ngoài phạm vi hiện tại.

| Nhóm | Tính năng | Trạng thái |
|---|---|---|
| Tài khoản | Đăng nhập (JWT), đổi mật khẩu, quản lý tài khoản, không khóa mất quản trị viên cuối cùng | Có |
| Phân quyền | Phạm vi theo cây đơn vị (đơn vị mình + trực thuộc), độ mật thường/mật theo vai trò; lọc trong truy vấn | Có |
| Kho văn bản | Tải lên nhiều tệp DOC/DOCX/PDF, chống trùng, kiểm tra nội dung tệp, giới hạn dung lượng cấu hình được | Có |
| Kho văn bản | Tệp gốc lưu trong kho đối tượng MinIO (S3); tải về dạng luồng, hỗ trợ `Range`; chuyển từ volume cũ bằng `python -m app.storage.migrate` | Có |
| Kho văn bản | Xử lý nền: đọc, trích xuất thông tin, độ mật (dấu mật hoặc người tải đánh dấu), lập chỉ mục; trạng thái và các bước hiển thị được | Có |
| Kho văn bản | Xem nội dung theo đoạn (có chỉ số nguồn để trích dẫn), tải tệp gốc, sửa thông tin tay, xử lý lại, xóa (xóa cả chỉ mục) | Có |
| Kho văn bản | Thẻ: hệ thống tự gắn năm, chủ đề (17 nhóm theo từ khóa trong trích yếu/đoạn đầu) và “Bản scan (OCR)”; người tải lên/quản trị gắn thêm tối đa 12 thẻ riêng (`PUT /api/documents/{id}/tags`), thẻ riêng không mất khi xử lý lại | Có |
| Kho văn bản | Duyệt kho: bảng bên trái có cây đơn vị gấp sẵn (số văn bản cả nhánh), chip loại văn bản / năm / thẻ kèm số lượng (`GET /api/documents/facets`); lọc nhiều loại (hoặc), nhiều thẻ (và); chip bộ lọc đang dùng bỏ được từng cái; bộ lọc, thẻ trạng thái và trang nằm trên URL nên gửi được cho người khác; bảng kéo đổi độ rộng, ẩn được và nhớ lựa chọn | Có |
| Kho văn bản | Nhập hàng loạt từ thư mục: `backend/tools/import_corpus.py` (đơn vị theo thư mục, thư mục “văn bản mật” thành mật, chạy lại không nhân đôi) và điền kết nối serving: `backend/tools/apply_serving.py` | Có |
| Tìm kiếm | Lai vector + BM25 trong Qdrant; chế độ hybrid/keyword/semantic; lọc theo loại, ký hiệu, số, cơ quan, trích yếu, ngày | Có |
| Tìm kiếm | Rerank (cohere/tei/intramind) xếp hạng lại các đoạn lấy từ tìm kiếm lai; lỗi thì giữ thứ tự ban đầu | Có |
| Quản trị | Cấu hình LLM, embedding, rerank, OCR, kiểm tra thể thức, lưu trữ; mã hóa API key; xác nhận máy chủ ngoài mạng nội bộ; kiểm tra kết nối | Có (API) |
| Quản trị | Lập chỉ mục lại khi đổi embedding | Có (lập lại toàn bộ; chưa chuyển đổi không gián đoạn) |
| Quản trị | Nhật ký kiểm toán | Có |
| Agent | Công cụ MCP trong phạm vi quyền của người hỏi (tìm, liệt kê, đọc, tóm tắt, tệp đính kèm, canvas); mỗi cuộc trò chuyện một tiến trình agent, danh tính người hỏi là token ký không đổi được | Có (kiểm thử đầu-cuối với mô hình giả; chưa thử mô hình thật) |
| Kiểm tra thể thức | Màn riêng, không lưu kho: kiểm tra TT68 + chính tả bằng `doccheck`, chọn chỗ sửa, Track Changes, tải bản sửa/ghi chú/báo cáo, lưu vào kho | Có |
| Kiểm tra chính tả | Màn riêng `/chinh-ta`, không lưu kho: dán văn bản hoặc chọn .docx/.doc/.pdf/.txt/.md, gạch sóng trên văn bản + danh sách theo loại lỗi (dấu thanh, âm tiết, khoảng cách, dấu câu, từ sai ngữ cảnh), chọn chỗ sửa, bỏ qua từ (danh sách theo phiên), Track Changes hoặc sửa thẳng, tải bản sửa/báo cáo; PDF chỉ liệt kê. Tài liệu: `docs/SPELLCHECK_API.md` | Có (chưa soát nền bằng mô hình GEC; bản scan chưa tự OCR) |
| Soát chính tả sâu | doccheck có ba lớp: từ điển + luật, n-gram âm tiết (`lm`), mô hình GECToR chạy ONNX trên CPU (`deep`, V3 chuẩn hoặc S3 nhanh). QK3 bật cả ba (Quản trị → Hệ thống → Kiểm tra thể thức: `spell_deep` off/auto/default/fast, `spell_deep_low`); tự trỏ doccheck tới thư viện ONNX Runtime của gói `onnxruntime`. Lưu ý giấy phép: trọng số GECToR ghi “Research use only” (một phần dữ liệu huấn luyện CC-BY-NC-SA) | Có (đã thử trên API thật) |
| Trợ lý | Chat hiển thị các bước đã làm (suy nghĩ, tìm song song), trích dẫn mở xem văn bản, tệp đính kèm nhanh, dừng giữa chừng, lịch sử trò chuyện | Có (câu trả lời đến một lần sau các bước) |
| Trợ lý | Tóm tắt (một lượt hoặc theo mục cho văn bản dài) | Có (thử với mô hình giả) |
| Trợ lý | Soạn thảo canvas theo mẫu TT68: 17 loại văn bản, quyền sở hữu từng phần, đề xuất chỉnh sửa chấp nhận/từ chối, kiểm tra thể thức, xuất DOCX, lưu kho | Có |
| Trợ lý | Bảng trong canvas: khối `table`/`appendix`, công thức và dòng cộng do server tính, ô `"…"`, `canvas_edit_table` (id dòng/cột + phiên bản khối), diff đề xuất theo ô, sửa ô/dòng/cột tại chỗ, nhãn số liệu đoạn văn đã đổi | Có (kiểm thử với mô hình giả; chưa thử mô hình thật; giao diện dựng được, chưa soát tay trên LLM giả) |
| Trợ lý | Văn phong quân sự theo đơn vị người soạn: quy tắc Thông tư 68 (có người duyệt) + hồ sơ văn phong đơn vị × loại văn bản học từ kho (bố cục, câu mở đầu/kết, căn cứ, nơi nhận, người ký, thuật ngữ; lùi lên cấp trên khi ít văn bản; bỏ văn bản mật) + văn bản mẫu gần chủ đề và đoạn mẫu theo mục trong phạm vi quyền (`canvas_style`); phong cách và mức chi tiết người dùng chọn trên Canvas; kiểm tra tất định số liệu/tên riêng/từ cần tránh trên từng đề xuất; phần đầu văn bản (cơ quan ban hành, ký hiệu, dòng Lưu) theo cách đơn vị thực sự ban hành | Có (kiểm thử với dữ liệu tổng hợp; đã dựng trên kho mẫu 3.356 văn bản; chưa thử với mô hình thật) |
| Trợ lý | Chữ trả lời hiện dần theo token | Chưa có (harness chỉ báo theo bước) |
| OCR | PDF scan qua Peppercorn v3 (endpoint OpenAI-compatible bên serving): vẽ trang, đọc, lưu `.ocr.docx`, lập chỉ mục; cả tệp đính kèm chat | Có (đã chạy thật với Peppercorn v3 trên 208 PDF scan của kho mẫu; PDF mà lớp chữ hỏng cũng được đọc bằng OCR) |
| Xem văn bản theo trang gốc | Trình duyệt vẽ **trang gốc bằng pdf.js** (đóng gói cục bộ, chạy offline): PDF gốc, hoặc PDF dựng từ tệp Word bằng LibreOffice (dựng một lần khi xử lý, lưu cạnh tệp gốc `<key>.view.pdf`, trình duyệt cache; `tools/build_previews.py` dựng bù) nên giữ nguyên phông, bảng, thể thức. Chỉ tải/vẽ các trang gần vùng nhìn thấy (HTTP Range), thu phóng, hiện số trang. Bản scan: OCR đọc theo khối (prompt `grounding`, `<key>.ocr.json`), khối vẽ lên trang gốc (rê chuột hiện khung và loại khối, nút “Hiện khối”, chữ ẩn nên chọn/chép/Ctrl+F được). Đoạn được trích dẫn sáng lên và cuộn tới (`?hl=` hoặc nguồn trong trợ lý): scan theo khối, PDF có lớp chữ theo tìm chuỗi trong lớp chữ. Chuyển “Trang gốc ⇄ Văn bản”; tệp không dựng được trang hoặc tệp đính kèm chat xem dạng văn bản. Khung chi tiết ở Kho kéo đổi độ rộng được (nhớ lại). API `GET /api/documents/{id}/preview` (Range), `/scan`, `/pages/{n}` (PNG, không còn dùng) | Có |
| Trích xuất thể thức TT68 | Cơ quan ban hành chỉ lấy các dòng in hoa trên số/ký hiệu; trích yếu ("V/v ...") là trường riêng; người ký tách chức vụ, cấp bậc, họ tên ("Phó Tham mưu trưởng, Đại tá, Nguyễn Ngọc Yên"); PDF ký số (trường chữ ký / ảnh con dấu không nằm trong lớp chữ) thì vẽ cả các trường đó rồi OCR trang đầu và các trang có dấu để bù số, ngày, người ký (`app/ocr/stamps.py`); đã có dấu/chữ ký mà vẫn thiếu số/ngày thì chuyển 'cần xem lại'; bản nháp chưa có số/ngày được để trống | Có |
| Kiểm duyệt đầu vào | Câu hỏi gõ vào trợ lý được rà bằng luật từ khóa (chuẩn hóa dấu/teen code/ký tự chèn) và model ViSoBERT-ViHSD ONNX int8 chạy CPU (~10 ms/tin, `tools/export_moderation_model.py`); nặng thì chặn, nhẹ thì cảnh báo, mọi lần ghi nhật ký `moderation.*` (người dùng, IP, cuộc trò chuyện, từ khớp, lần thứ N trong 30 ngày); cấu hình ở Quản trị → Hệ thống → Kiểm duyệt đầu vào | Có; chưa rà tài liệu tải lên |
| Giao diện | Hệ thiết kế QK3 (`design-system/qk3-documents/`): token sáng/tối, phông Be Vietnam Pro + Tinos và icon đóng gói sẵn (chạy offline), vỏ ứng dụng (sidebar thu gọn, breadcrumb, Ctrl+K, chỉ báo tác vụ nền), bộ component dùng chung, đăng nhập | Có |
| Giao diện | Trang Kho, Kiểm tra thể thức, Kiểm tra chính tả, Quản trị theo thiết kế mới | Có |
| Giao diện | Trang Trợ lý + Canvas theo thiết kế mới | Đang làm |
| Thống kê | Trang `/thong-ke` (admin, chỉ huy; chỉ huy chỉ thấy đơn vị mình và trực thuộc): văn bản theo loại, đơn vị, trạng thái, tháng tải lên, năm ban hành, chủ đề; câu hỏi trợ lý theo ngày; sử dụng theo đơn vị (tài khoản hoạt động, câu hỏi, văn bản tải lên, vi phạm, sparkline); kiểm duyệt đầu vào; kỳ 7/30/90 ngày trên URL; biểu đồ SVG tự vẽ, có chế độ xem bảng số liệu; API `GET /api/stats` | Có |
| Báo cáo xuất tệp | Xuất thống kê ra Word/Excel | Chưa có |
| Tích hợp | Hệ thống quản lý văn bản sẵn có; ký số; phê duyệt/phát hành | Chưa có |
| Bảo mật vận hành | HTTPS/TLS, LDAP/AD, hardening, kiểm thử xâm nhập | Cần triển khai/kiểm chứng theo môi trường đơn vị |

Không dùng dữ liệu mật/nhạy cảm nếu chưa có phê duyệt và biện pháp bảo vệ phù hợp.
