import { initials } from '../lib/format'

interface AvatarProps {
  /** Full name; the initials are derived from it. */
  name: string
  size?: 'sm' | 'md' | 'lg'
  /** For use on the navy sidebar. */
  onDark?: boolean
  className?: string
}

/** Round initials badge. Decorative: the name should appear in text next to it. */
export function Avatar({ name, size = 'md', onDark, className }: AvatarProps) {
  return (
    <span className={['avatar', size !== 'md' && `avatar--${size}`, onDark && 'avatar--on-dark', className].filter(Boolean).join(' ')} aria-hidden="true">
      {initials(name)}
    </span>
  )
}
