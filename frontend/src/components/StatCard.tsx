import type { ReactNode } from 'react'
import { Icon, type IconName } from './Icon'
import { Skeleton } from './Skeleton'

interface StatCardProps {
  label: string
  /** The number (already formatted). */
  value: ReactNode
  /** Small line under the number ("+3 hôm nay"). */
  hint?: ReactNode
  icon?: IconName
  tone?: 'brand' | 'ok' | 'info' | 'warn' | 'danger'
  /** Makes the card a toggle button (a filter). */
  onClick?: () => void
  /** Pressed state of a filter card. */
  selected?: boolean
  loading?: boolean
}

/** KPI tile. With `onClick` it is a filter button (`aria-pressed`); a row of them goes inside `<div className="stat-grid">`. */
export function StatCard({ label, value, hint, icon, tone = 'brand', onClick, selected, loading }: StatCardProps) {
  const body = (
    <>
      <span className="stat__head">
        <span className="stat__label">{label}</span>
        {icon && <span className="stat__icon"><Icon name={icon} size={16} /></span>}
      </span>
      <span className="stat__value">{loading ? <Skeleton width={64} height={28} /> : value}</span>
      {hint && <span className="stat__hint">{hint}</span>}
    </>
  )
  const classes = ['stat', tone !== 'brand' && `stat--${tone}`].filter(Boolean).join(' ')
  return onClick ? (
    <button type="button" className={classes} aria-pressed={selected ?? false} onClick={onClick}>{body}</button>
  ) : (
    <div className={classes}>{body}</div>
  )
}
