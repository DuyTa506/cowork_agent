import type { Role } from '../../api'
import type { IconName } from '../Icon'

export interface NavEntry {
  to: string
  label: string
  icon: IconName
  /** One line shown under the label in the command palette. */
  description: string
  /** Extra words the command palette matches on. */
  keywords: string[]
  adminOnly?: boolean
  /** Administrators and commanders only (unit-wide figures). */
  viewerOnly?: boolean
}

/** Whether a user of `role` is offered this entry. */
export function canSee(entry: NavEntry, role: Role | undefined): boolean {
  if (entry.adminOnly) return role === 'admin'
  if (entry.viewerOnly) return role === 'admin' || role === 'commander'
  return true
}

/** Main navigation, in display order. The sidebar, the top-bar breadcrumb and the command palette all read this list. */
export const NAV: NavEntry[] = [
  { to: '/tro-ly', label: 'Trợ lý AI', icon: 'chat', description: 'Hỏi đáp, tóm tắt và soạn thảo với trợ lý', keywords: ['hỏi đáp', 'chat', 'soạn thảo', 'canvas', 'tóm tắt'] },
  { to: '/kho', label: 'Kho văn bản', icon: 'folder', description: 'Tra cứu và quản lý văn bản', keywords: ['tra cứu', 'tìm kiếm', 'văn bản', 'tải lên', 'quyết định', 'kế hoạch'] },
  { to: '/thong-ke', label: 'Thống kê', icon: 'fileBarChart', description: 'Số liệu văn bản và mức sử dụng của các đơn vị', keywords: ['thống kê', 'biểu đồ', 'dashboard', 'báo cáo', 'sử dụng', 'số liệu', 'phòng ban'], viewerOnly: true },
  { to: '/kiem-tra', label: 'Kiểm tra thể thức', icon: 'shield', description: 'Đối chiếu một tệp với thể thức quy định', keywords: ['thể thức', 'định dạng', 'thông tư 68', 'lỗi'] },
  { to: '/chinh-ta', label: 'Kiểm tra chính tả', icon: 'spellcheck', description: 'Soát chính tả văn bản dán hoặc một tệp', keywords: ['chính tả', 'sai dấu', 'gõ sai', 'soát lỗi', 'tiếng việt'] },
  { to: '/quan-tri', label: 'Quản trị hệ thống', icon: 'sliders', description: 'Tài khoản, nhật ký, cấu hình mô hình', keywords: ['tài khoản', 'người dùng', 'nhật ký', 'cấu hình', 'mô hình'], adminOnly: true },
]
