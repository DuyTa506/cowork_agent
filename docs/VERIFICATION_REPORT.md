# Báo cáo kiểm tra bản MVP 0.1.0

Ngày kiểm tra: 14/10/2026

## Đã kiểm tra thành công

- Biên dịch cú pháp Python (`compileall`) cho backend và tests.
- 4 bài kiểm thử đơn vị của dịch vụ AI baseline.
- Kiểm thử tích hợp backend bằng FastAPI TestClient với SQLite tạm: health, đăng nhập, thông tin tài khoản, dashboard, bộ quy tắc, tải DOCX, kiểm tra, tóm tắt, trích xuất, phân loại, tìm kiếm, hỏi đáp, danh sách người dùng quản trị.
- Phân tích cú pháp TypeScript/TSX của các tệp frontend bằng TypeScript transpile API.
- Đọc/kiểm tra cấu trúc YAML của `docker-compose.yml`.

## Chưa xác minh trong môi trường tạo gói

- Chưa chạy `npm run build`: không thể hoàn tất cài đặt npm dependencies trong môi trường này do kết nối registry bị timeout. Cần chạy `npm install` và `npm run build` trên máy phát triển có quyền tải các gói đã được phê duyệt.
- Chưa build/chạy Docker image vì Docker Engine không có sẵn trong môi trường tạo gói. Thực hiện kiểm tra `docker compose build` trên máy build có Docker.
- Chưa kiểm thử tải đồng thời, kiểm thử xâm nhập, đánh giá độ chính xác trên bộ dữ liệu nghiệp vụ gán nhãn, hoặc nghiệm thu với người dùng.

## Diễn giải

Đây là MVP có thể phát triển và thử nghiệm; các chức năng AI hiện dùng rule/heuristic, phân loại từ khóa, trích xuất regex và baseline tóm tắt/hỏi đáp khi không cấu hình LLM nội bộ. Không coi điểm kiểm tra là độ chính xác AI chính thức. Chỉ sử dụng dữ liệu được phép và không đưa tài liệu mật/nhạy cảm vào hệ thống trước khi được cấp có thẩm quyền phê duyệt, rà soát bảo mật và nghiệm thu.
