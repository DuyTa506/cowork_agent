import type { ReactNode } from 'react'
import { Icon, type IconName } from './Icon'
import { IconButton } from './IconButton'

interface AlertProps {
  kind?: 'error' | 'warning' | 'info' | 'success'
  title?: string
  children?: ReactNode
  /** Optional action (a Button) shown on the right. */
  action?: ReactNode
  /** Adds a close button. */
  onClose?: () => void
}

const ICONS: Record<NonNullable<AlertProps['kind']>, IconName> = {
  error: 'alertCircle',
  warning: 'alert',
  info: 'info',
  success: 'checkCircle',
}

/** Inline message next to the thing it is about: icon, bold title, text, optional action. Errors are announced at once. */
export function Alert({ kind = 'info', title, children, action, onClose }: AlertProps) {
  return (
    <div className={`alert alert--${kind}`} role={kind === 'error' ? 'alert' : 'status'}>
      <Icon name={ICONS[kind]} size={18} className="alert__icon" />
      <div className="alert__body">
        {title && <strong className="alert__title">{title}</strong>}
        {children && <div className="alert__text">{children}</div>}
      </div>
      {action && <div className="alert__action">{action}</div>}
      {onClose && <IconButton icon="close" label="Đóng" size="sm" className="alert__close" onClick={onClose} />}
    </div>
  )
}
