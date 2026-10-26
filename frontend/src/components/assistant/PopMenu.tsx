import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type CSSProperties, type KeyboardEvent, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Icon, type IconName } from '../Icon'

export interface MenuItem {
  key: string
  label: string
  icon?: IconName
  /** Shown as a checkbox item (`menuitemcheckbox`) with a tick while true. */
  checked?: boolean
  danger?: boolean
  disabled?: boolean
  /** A short explanation under the label. */
  hint?: string
  onSelect: () => void
}

interface PopMenuProps {
  /** Accessible name of the menu. */
  label: string
  items: MenuItem[]
  /** Which side of the trigger the menu opens on. */
  placement?: 'top' | 'bottom'
  /** Align the menu's edge with the start (left) or the end (right) of the trigger. */
  align?: 'start' | 'end'
  /** Menu width in pixels (default 252). */
  width?: number
  /** Renders the trigger; spread `props` on a `<button>`. */
  trigger: (props: TriggerProps) => ReactNode
  className?: string
}

export interface TriggerProps {
  ref: (element: HTMLButtonElement | null) => void
  'aria-haspopup': 'menu'
  'aria-expanded': boolean
  'aria-controls': string | undefined
  onClick: () => void
  onKeyDown: (event: KeyboardEvent<HTMLButtonElement>) => void
}

const MENU_WIDTH = 252

/**
 * A button that opens a small menu (arrow keys, Escape, outside click). The menu is positioned against the viewport
 * (portal + fixed), so it is never clipped by a scrolling parent such as the conversation list.
 */
export function PopMenu({ label, items, placement = 'bottom', align = 'end', width: menuWidth = MENU_WIDTH, trigger, className }: PopMenuProps) {
  const [open, setOpen] = useState(false)
  const [style, setStyle] = useState<CSSProperties>({})
  const triggerRef = useRef<HTMLButtonElement | null>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const menuId = useId()

  const place = useCallback(() => {
    const button = triggerRef.current
    if (!button) return
    const rect = button.getBoundingClientRect()
    const width = Math.min(menuWidth, window.innerWidth - 16)
    const left = align === 'end' ? rect.right - width : rect.left
    const next: CSSProperties = { left: Math.max(8, Math.min(left, window.innerWidth - width - 8)), width }
    if (placement === 'top') next.bottom = window.innerHeight - rect.top + 6
    else next.top = rect.bottom + 6
    setStyle(next)
  }, [align, placement, menuWidth])

  useLayoutEffect(() => {
    if (open) place()
  }, [open, place])

  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node
      if (!menuRef.current?.contains(target) && !triggerRef.current?.contains(target)) setOpen(false)
    }
    const close = () => setOpen(false)
    document.addEventListener('pointerdown', onPointerDown)
    window.addEventListener('resize', close)
    window.addEventListener('scroll', close, true)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      window.removeEventListener('resize', close)
      window.removeEventListener('scroll', close, true)
    }
  }, [open])

  useEffect(() => {
    if (open) menuRef.current?.querySelector<HTMLElement>('[role^="menuitem"]:not(:disabled)')?.focus()
  }, [open])

  const close = (refocus: boolean) => {
    setOpen(false)
    if (refocus) triggerRef.current?.focus()
  }

  const onMenuKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      event.stopPropagation()
      close(true)
      return
    }
    if (event.key === 'Tab') {
      setOpen(false)
      return
    }
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp' && event.key !== 'Home' && event.key !== 'End') return
    event.preventDefault()
    const nodes = Array.from(menuRef.current?.querySelectorAll<HTMLElement>('[role^="menuitem"]:not(:disabled)') ?? [])
    if (nodes.length === 0) return
    const index = nodes.indexOf(document.activeElement as HTMLElement)
    const next =
      event.key === 'Home' ? 0 : event.key === 'End' ? nodes.length - 1 : (index + (event.key === 'ArrowDown' ? 1 : -1) + nodes.length) % nodes.length
    nodes[next]?.focus()
  }

  return (
    <>
      {trigger({
        ref: (element) => {
          triggerRef.current = element
        },
        'aria-haspopup': 'menu',
        'aria-expanded': open,
        'aria-controls': open ? menuId : undefined,
        onClick: () => setOpen((value) => !value),
        onKeyDown: (event) => {
          if ((event.key === 'ArrowDown' || event.key === 'ArrowUp') && !open) {
            event.preventDefault()
            setOpen(true)
          }
        },
      })}
      {open &&
        createPortal(
          <div className={['popmenu', className].filter(Boolean).join(' ')} id={menuId} role="menu" aria-label={label} ref={menuRef} style={style} onKeyDown={onMenuKeyDown}>
            {items.map((item) => (
              <button
                key={item.key}
                type="button"
                role={item.checked === undefined ? 'menuitem' : 'menuitemcheckbox'}
                aria-checked={item.checked}
                disabled={item.disabled}
                className={item.danger ? 'popmenu__item popmenu__item--danger' : 'popmenu__item'}
                onClick={() => {
                  close(true)
                  item.onSelect()
                }}
              >
                {item.icon && <Icon name={item.icon} size={18} className="popmenu__icon" />}
                <span className="popmenu__text">
                  {item.label}
                  {item.hint && <small>{item.hint}</small>}
                </span>
                {item.checked && <Icon name="check" size={16} className="popmenu__tick" />}
              </button>
            ))}
          </div>,
          document.body,
        )}
    </>
  )
}
