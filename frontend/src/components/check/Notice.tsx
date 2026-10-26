import type { ReactNode } from 'react'
import { Icon, type IconName } from '../Icon'
import type { FailureKind, FailureText } from './model'

type NoticeTone = 'danger' | 'warning' | 'info' | 'success'

interface NoticeProps {
  tone: NoticeTone
  icon: IconName
  title: string
  children?: ReactNode
  /** Buttons for the next step. */
  actions?: ReactNode
  className?: string
}

/** Calm callout: a tinted tile with the icon, the title, one explanation and the next action. Errors are announced at once. */
export function Notice({ tone, icon, title, children, actions, className }: NoticeProps) {
  return (
    <div className={['check-notice', `check-notice--${tone}`, className].filter(Boolean).join(' ')} role={tone === 'danger' ? 'alert' : 'status'}>
      <span className="check-notice__icon"><Icon name={icon} size={20} weight="fill" /></span>
      <div className="check-notice__body">
        <strong className="check-notice__title">{title}</strong>
        {children && <div className="check-notice__text">{children}</div>}
        {actions && <div className="check-notice__actions">{actions}</div>}
      </div>
    </div>
  )
}

const FAILURE_VIEW: Record<FailureKind, { icon: IconName; tone: NoticeTone; next: string }> = {
  unsupported: { icon: 'fileX', tone: 'danger', next: 'Chọn tệp Word (.docx, .doc) hoặc PDF.' },
  too_large: { icon: 'fileX', tone: 'danger', next: 'Giảm dung lượng tệp (xóa ảnh, nén ảnh trong Word) rồi chọn lại.' },
  empty: { icon: 'fileX', tone: 'danger', next: 'Mở tệp để kiểm tra có nội dung, rồi chọn lại.' },
  scan: { icon: 'scan', tone: 'warning', next: 'Dùng bản PDF có lớp chữ hoặc tệp Word gốc. Bản scan phải qua nhận dạng chữ (OCR) trước.' },
  invalid: { icon: 'alertCircle', tone: 'danger', next: 'Mở tệp bằng Word, lưu thành tệp .docx mới rồi chọn lại.' },
  gone: { icon: 'clock', tone: 'warning', next: 'Tệp tạm đã bị xóa hoặc hết hạn. Hãy chọn tệp lại để kiểm tra.' },
  network: { icon: 'alertCircle', tone: 'danger', next: 'Kiểm tra kết nối mạng nội bộ rồi thử lại.' },
  generic: { icon: 'alertCircle', tone: 'danger', next: '' },
}

/** A failed request or an unusable file, with what to do about it. */
export function FailureNotice({ failure, actions }: { failure: FailureText; actions?: ReactNode }) {
  const view = FAILURE_VIEW[failure.kind ?? 'generic']
  return (
    <Notice tone={view.tone} icon={view.icon} title={failure.title} actions={actions}>
      <p>{failure.message}</p>
      {view.next && <p className="check-notice__next">{view.next}</p>}
    </Notice>
  )
}
