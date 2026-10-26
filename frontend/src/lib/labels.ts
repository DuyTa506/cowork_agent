import type { DocumentLevel, DocumentState, Role, StepState } from '../api'

export type Tone = 'green' | 'blue' | 'amber' | 'red' | 'grey'

export const ROLE_LABELS: Record<Role, string> = {
  admin: 'Quản trị viên',
  commander: 'Chỉ huy',
  reviewer: 'Cán bộ rà soát',
  staff: 'Cán bộ, nhân viên',
}

export const ROLES: Role[] = ['admin', 'commander', 'reviewer', 'staff']

export const LEVEL_LABELS: Record<DocumentLevel, string> = { thuong: 'Thường', mat: 'Mật' }

export const STATE_LABELS: Record<DocumentState, string> = {
  uploaded: 'Chờ xử lý',
  processing: 'Đang xử lý',
  ready: 'Sẵn sàng',
  needs_review: 'Cần rà soát',
  needs_ocr: 'Cần OCR',
  failed: 'Lỗi',
}

export const STATE_TONES: Record<DocumentState, Tone> = {
  uploaded: 'blue',
  processing: 'blue',
  ready: 'green',
  needs_review: 'amber',
  needs_ocr: 'grey',
  failed: 'red',
}

export const STEP_TONES: Record<StepState, Tone> = { pending: 'grey', running: 'blue', done: 'green', failed: 'red' }

/** Types the parser recognises; used for the filter and as suggestions when correcting a document. */
export const DOCUMENT_TYPES = [
  'Quyết định', 'Kế hoạch', 'Báo cáo', 'Tờ trình', 'Thông báo', 'Hướng dẫn', 'Chỉ thị', 'Nghị quyết', 'Biên bản',
  'Quy chế', 'Quy định', 'Mệnh lệnh', 'Chương trình', 'Đề án', 'Phương án', 'Giấy mời', 'Giấy giới thiệu', 'Thông tư',
  'Kết luận', 'Nội quy', 'Danh sách', 'Thông tri', 'Lệnh', 'Công điện', 'Công văn',
]

/** Vietnamese names for audit-trail action codes; unknown codes are shown as they are. */
export const AUDIT_ACTION_LABELS: Record<string, string> = {
  'auth.login': 'Đăng nhập',
  'auth.login_failed': 'Đăng nhập thất bại',
  'auth.change_password': 'Đổi mật khẩu',
  'document.upload': 'Tải văn bản lên',
  'document.view': 'Xem văn bản',
  'document.download': 'Tải tệp gốc',
  'document.update': 'Sửa thông tin văn bản',
  'document.reprocess': 'Xử lý lại văn bản',
  'document.delete': 'Xóa văn bản',
  'user.create': 'Tạo tài khoản',
  'user.update': 'Sửa tài khoản',
  'settings.save': 'Lưu cấu hình hệ thống',
  'index.rebuild': 'Lập chỉ mục lại',
  'format_check.run': 'Kiểm tra thể thức',
  'format_check.fix': 'Sửa thể thức',
  'spellcheck.run': 'Kiểm tra chính tả',
  'spellcheck.fix': 'Sửa chính tả',
  'moderation.block': 'Chặn tin nhắn vi phạm',
  'moderation.warn': 'Cảnh báo tin nhắn vi phạm',
  'moderation.log': 'Ghi nhận tin nhắn vi phạm',
}
