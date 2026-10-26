import type { ReactNode } from 'react'
import { EmptyIllustration, type IllustrationName } from './EmptyIllustrations'
import { Icon, type IconName } from './Icon'

export type { IllustrationName }

interface EmptyStateProps {
  /** Line illustration (default `documents`). */
  illustration?: IllustrationName
  /** Older alternative: a plain icon in a circle instead of an illustration. */
  icon?: IconName
  title: string
  description?: ReactNode
  /** One primary action (a Button); several are laid out side by side. */
  action?: ReactNode
  /** Less padding and a smaller picture, for panels and drawers. */
  compact?: boolean
}

/** Placeholder for a list or page with nothing to show: say what is missing and what to do next. */
export function EmptyState({ illustration, icon, title, description, action, compact }: EmptyStateProps) {
  return (
    <div className={['empty', compact && 'empty--compact'].filter(Boolean).join(' ')}>
      {icon && !illustration ? <span className="empty__icon"><Icon name={icon} size={26} /></span> : <EmptyIllustration name={illustration ?? 'documents'} />}
      <h2 className="empty__title">{title}</h2>
      {description && <p className="empty__text">{description}</p>}
      {action && <div className="empty__action">{action}</div>}
    </div>
  )
}
