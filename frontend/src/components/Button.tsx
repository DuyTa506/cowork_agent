import type { ButtonHTMLAttributes } from 'react'
import { Icon, type IconName } from './Icon'
import { Spinner } from './Spinner'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** `default` and `secondary` are the same white button with a strong border. `danger-solid` only inside confirm dialogs. */
  variant?: 'default' | 'secondary' | 'primary' | 'ghost' | 'danger' | 'danger-solid'
  /** 28 px (`sm`), 36 px (`md`, default) or 44 px (`lg`, login and hero actions). */
  size?: 'sm' | 'md' | 'lg'
  /** Leading icon. */
  icon?: IconName
  /** Trailing icon (menus, "next"). */
  iconEnd?: IconName
  /** Shows a spinner in place of the leading icon and disables the button; the label stays. */
  loading?: boolean
  /** Full width. */
  block?: boolean
}

/** Text button; `type` defaults to "button" so it never submits a form by accident. One primary button per screen. */
export function Button({ variant = 'default', size = 'md', icon, iconEnd, loading = false, block, className, children, disabled, type = 'button', ...rest }: ButtonProps) {
  const classes = [
    'btn',
    variant !== 'default' && variant !== 'secondary' && `btn--${variant}`,
    size !== 'md' && `btn--${size}`,
    block && 'btn--block',
    className,
  ]
    .filter(Boolean)
    .join(' ')
  const iconSize = size === 'sm' ? 16 : 18
  return (
    <button type={type} className={classes} disabled={disabled || loading} aria-busy={loading || undefined} {...rest}>
      {loading ? <Spinner size={14} /> : icon ? <Icon name={icon} size={iconSize} /> : null}
      {children}
      {iconEnd && !loading && <Icon name={iconEnd} size={iconSize} />}
    </button>
  )
}
