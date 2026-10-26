import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { Icon, type IconName } from '../Icon'

export interface MenuItem {
  key: string
  label: string
  /** Second line, for example how many rows the choice affects. */
  description?: string
  icon?: IconName
  disabled?: boolean
  /** Draws a hairline above the item. */
  separatorBefore?: boolean
  onSelect: () => void
}

interface MenuProps {
  /** Visible text of the button. */
  label: ReactNode
  /** Accessible name when it differs from the visible text. */
  ariaLabel?: string
  icon?: IconName
  items: MenuItem[]
  /** Which edge of the button the list lines up with. */
  align?: 'start' | 'end'
  /** Opens upwards (for a menu in the bar at the bottom of the screen). */
  direction?: 'down' | 'up'
  disabled?: boolean
  className?: string
}

/**
 * Button that opens a list of actions (WAI-ARIA menu button): Esc closes and returns focus, arrow keys move, a click outside closes.
 * Used for "quick select" in the findings list and for the secondary actions of the bottom bar on narrow screens.
 */
export function Menu({ label, ariaLabel, icon, items, align = 'start', direction = 'down', disabled, className }: MenuProps) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const listId = useId()

  useEffect(() => {
    if (!open) return
    const onPointer = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', onPointer)
    return () => document.removeEventListener('pointerdown', onPointer)
  }, [open])

  // Focus the first enabled choice when the list opens from the keyboard or the mouse.
  useEffect(() => {
    if (open) rootRef.current?.querySelector<HTMLButtonElement>('[role="menuitem"]:not(:disabled)')?.focus()
  }, [open])

  const move = (step: 1 | -1 | 'first' | 'last') => {
    const nodes = [...(rootRef.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]:not(:disabled)') ?? [])]
    if (nodes.length === 0) return
    const index = nodes.indexOf(document.activeElement as HTMLButtonElement)
    const next = step === 'first' ? 0 : step === 'last' ? nodes.length - 1 : (index + step + nodes.length) % nodes.length
    nodes[next]?.focus()
  }

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!open) return
    if (event.key === 'Escape') {
      event.preventDefault()
      event.stopPropagation()
      setOpen(false)
      buttonRef.current?.focus()
    } else if (event.key === 'ArrowDown') {
      event.preventDefault()
      move(1)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      move(-1)
    } else if (event.key === 'Home') {
      event.preventDefault()
      move('first')
    } else if (event.key === 'End') {
      event.preventDefault()
      move('last')
    } else if (event.key === 'Tab') {
      setOpen(false)
    }
  }

  return (
    <div className={['check-menu', className].filter(Boolean).join(' ')} ref={rootRef} onKeyDown={onKeyDown}>
      <button
        ref={buttonRef}
        type="button"
        className="btn check-menu__btn"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-label={ariaLabel}
        disabled={disabled}
        onClick={() => setOpen((value) => !value)}
      >
        {icon && <Icon name={icon} size={16} />}
        <span>{label}</span>
        <Icon name="chevronDown" size={14} className="check-menu__caret" />
      </button>
      {open && (
        <div className={`check-menu__pop check-menu__pop--${align} check-menu__pop--${direction}`} role="menu" id={listId} aria-label={ariaLabel}>
          {items.map((item) => (
            <div key={item.key} className="check-menu__row" role="none">
              {item.separatorBefore && <hr className="check-menu__sep" />}
              <button
                type="button"
                role="menuitem"
                className="check-menu__item"
                disabled={item.disabled}
                onClick={() => {
                  setOpen(false)
                  buttonRef.current?.focus()
                  item.onSelect()
                }}
              >
                {item.icon && <Icon name={item.icon} size={16} />}
                <span className="check-menu__text">
                  <span>{item.label}</span>
                  {item.description && <span className="check-menu__desc">{item.description}</span>}
                </span>
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
