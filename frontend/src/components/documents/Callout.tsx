import type { ReactNode } from 'react'
import { Icon, type IconName } from '../Icon'

interface CalloutProps {
  tone: 'warning' | 'danger' | 'info' | 'secret'
  icon?: IconName
  title?: string
  children?: ReactNode
}

const DEFAULT_ICONS: Record<CalloutProps['tone'], IconName> = { warning: 'alert', danger: 'alertCircle', info: 'info', secret: 'lock' }

/** A real warning box: tinted background, status bar on the left, icon, bold title and body (never colour alone). */
export function Callout({ tone, icon, title, children }: CalloutProps) {
  return (
    <div className={`dcallout dcallout--${tone}`} role={tone === 'danger' ? 'alert' : 'status'}>
      <Icon name={icon ?? DEFAULT_ICONS[tone]} size={20} weight="fill" className="dcallout__icon" />
      <div className="dcallout__body">
        {title && <strong className="dcallout__title">{title}</strong>}
        {children && <div className="dcallout__text">{children}</div>}
      </div>
    </div>
  )
}
