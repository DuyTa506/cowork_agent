import type { ReactNode } from 'react'
import type { Tone } from '../lib/labels'

export { Badge } from './Chip'

/** Status text with a coloured dot (the dot is decorative; the text carries the meaning). For important states prefer `Chip`. */
export function StatusDot({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span className="status">
      <i className={`status__dot tone-bg--${tone}`} aria-hidden="true" />
      {children}
    </span>
  )
}
