import type { ButtonHTMLAttributes } from 'react'
import { Icon, type IconName } from './Icon'
import { Tooltip } from './Tooltip'

export interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'aria-label'> {
  icon: IconName
  /** Required: icon-only buttons need an accessible name; it is also the tooltip text. */
  label: string
  /** Button size: `sm` 28, `md` 36 (default), `lg` 44 px. A number is the icon size in px (older call sites); the button stays 36 px. */
  size?: 'sm' | 'md' | 'lg' | number
  /** Same as `size="sm"`. */
  compact?: boolean
  /** Draws a border (toolbars). */
  outline?: boolean
  /** Red on hover (delete). */
  danger?: boolean
  /** Tooltip placement; `false` turns the tooltip off. */
  tooltip?: 'top' | 'bottom' | 'left' | 'right' | false
}

/** Square icon-only button with a tooltip. Pass `aria-pressed` / `aria-expanded` for toggles. */
export function IconButton({ icon, label, size = 'md', compact, outline, danger, tooltip = 'top', className, type = 'button', ...rest }: IconButtonProps) {
  const step = compact ? 'sm' : typeof size === 'number' ? 'md' : size
  const iconSize = typeof size === 'number' ? size : step === 'sm' ? 16 : step === 'lg' ? 22 : 18
  const classes = ['icon-btn', step !== 'md' && `icon-btn--${step}`, outline && 'icon-btn--outline', danger && 'icon-btn--danger', className].filter(Boolean).join(' ')
  const button = (
    <button type={type} className={classes} aria-label={label} {...rest}>
      <Icon name={icon} size={iconSize} />
    </button>
  )
  return tooltip === false || rest.disabled ? button : <Tooltip content={label} side={tooltip}>{button}</Tooltip>
}
