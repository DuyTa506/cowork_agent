import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Icon, type IconName } from './Icon'

export type MenuEntry =
  | { type?: 'item'; key: string; label: string; icon?: IconName; hint?: string; danger?: boolean; disabled?: boolean; onSelect: () => void }
  | { type: 'separator'; key: string }
  | { type: 'label'; key: string; label: string }
  | { type: 'header'; key: string; title: string; subtitle?: string }

export type MenuPlacement = 'bottom-start' | 'bottom-end' | 'top-start' | 'top-end'

/** Props to spread on the element that opens the menu. */
export interface MenuTriggerProps {
  ref: (element: HTMLElement | null) => void
  onClick: () => void
  onKeyDown: (event: KeyboardEvent<HTMLElement>) => void
  'aria-haspopup': 'menu'
  'aria-expanded': boolean
  'aria-controls': string | undefined
}

interface MenuProps {
  /** Accessible name of the menu ("Tài khoản", "Thao tác"). */
  label: string
  items: MenuEntry[]
  /** Render the opener: `trigger={(props) => <button {...props}>…</button>}`. */
  trigger: (props: MenuTriggerProps, state: { open: boolean }) => ReactNode
  placement?: MenuPlacement
}

const GAP = 6
const MARGIN = 8

/**
 * Dropdown menu. Keyboard: Enter / Space / ArrowDown on the opener open it, Up / Down / Home / End / letters move,
 * Enter selects, Esc closes and returns focus, Tab closes. Focus goes back to the opener before `onSelect` runs, so an item can
 * safely open a dialog.
 */
export function Menu({ label, items, trigger, placement = 'bottom-end' }: MenuProps) {
  const id = useId()
  const [open, setOpen] = useState(false)
  const anchorRef = useRef<HTMLElement | null>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const focusFirst = useRef(false)

  const close = useCallback((restoreFocus = true) => {
    setOpen(false)
    if (restoreFocus) anchorRef.current?.focus({ preventScroll: true })
  }, [])

  useLayoutEffect(() => {
    if (!open) return
    const anchor = anchorRef.current
    const menu = menuRef.current
    if (!anchor || !menu) return
    const a = anchor.getBoundingClientRect()
    const m = menu.getBoundingClientRect()
    let top = placement.startsWith('top') ? a.top - m.height - GAP : a.bottom + GAP
    if (placement.startsWith('top') && top < MARGIN) top = a.bottom + GAP
    if (placement.startsWith('bottom') && top + m.height > window.innerHeight - MARGIN && a.top - m.height - GAP > MARGIN) top = a.top - m.height - GAP
    let left = placement.endsWith('end') ? a.right - m.width : a.left
    left = Math.min(Math.max(MARGIN, left), window.innerWidth - m.width - MARGIN)
    menu.style.top = `${top}px`
    menu.style.left = `${left}px`
  }, [open, placement])

  useEffect(() => {
    if (!open) return
    const menu = menuRef.current
    if (menu) {
      const first = menu.querySelector<HTMLElement>('[role="menuitem"]:not(:disabled)')
      ;(focusFirst.current ? first : menu)?.focus({ preventScroll: true })
    }
    const onPointer = (event: globalThis.MouseEvent) => {
      const target = event.target as Node
      if (!menuRef.current?.contains(target) && !anchorRef.current?.contains(target)) close(false)
    }
    // Capture phase + stopImmediatePropagation: Esc closes only the menu, not the drawer or dialog behind it.
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopImmediatePropagation()
        event.preventDefault()
        close()
      } else if (event.key === 'Tab') {
        close(false)
      }
    }
    const onScroll = (event: Event) => {
      if (!menuRef.current?.contains(event.target as Node)) close(false)
    }
    document.addEventListener('mousedown', onPointer)
    document.addEventListener('keydown', onKey, true)
    window.addEventListener('scroll', onScroll, true)
    const onResize = () => close(false)
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('resize', onResize)
      document.removeEventListener('mousedown', onPointer)
      document.removeEventListener('keydown', onKey, true)
      window.removeEventListener('scroll', onScroll, true)
      focusFirst.current = false
    }
  }, [open, close])

  const onTriggerKey = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      focusFirst.current = true
      setOpen(true)
    } else if ((event.key === 'Enter' || event.key === ' ') && !open) {
      focusFirst.current = true // the click that follows opens it
    }
  }

  const onMenuKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const nodes = Array.from(menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]:not(:disabled)') ?? [])
    if (nodes.length === 0) return
    const index = nodes.indexOf(document.activeElement as HTMLElement)
    let next: HTMLElement | undefined
    if (event.key === 'ArrowDown') next = nodes[(index + 1) % nodes.length]
    else if (event.key === 'ArrowUp') next = nodes[(index - 1 + nodes.length) % nodes.length]
    else if (event.key === 'Home') next = nodes[0]
    else if (event.key === 'End') next = nodes[nodes.length - 1]
    else if (event.key.length === 1 && /\S/.test(event.key)) {
      const letter = event.key.toLowerCase()
      next = [...nodes.slice(index + 1), ...nodes.slice(0, index + 1)].find((node) => node.textContent?.trim().toLowerCase().startsWith(letter))
    } else return
    event.preventDefault()
    next?.focus()
  }

  const select = (entry: Extract<MenuEntry, { onSelect: () => void }>) => {
    close()
    entry.onSelect()
  }

  const triggerProps: MenuTriggerProps = {
    ref: (element) => {
      anchorRef.current = element
    },
    onClick: () => {
      if (open) close()
      else setOpen(true)
    },
    onKeyDown: onTriggerKey,
    'aria-haspopup': 'menu',
    'aria-expanded': open,
    'aria-controls': open ? id : undefined,
  }

  return (
    <>
      {trigger(triggerProps, { open })}
      {open &&
        createPortal(
          <div
            ref={menuRef}
            id={id}
            className="menu"
            role="menu"
            aria-label={label}
            tabIndex={-1}
            onKeyDown={onMenuKey}
          >
            {items.map((entry) => {
              if (entry.type === 'separator') return <div key={entry.key} className="menu__sep" role="separator" />
              if (entry.type === 'label') return <div key={entry.key} className="menu__label" role="presentation">{entry.label}</div>
              if (entry.type === 'header') {
                return (
                  <div key={entry.key} className="menu__header" role="presentation">
                    <strong>{entry.title}</strong>
                    {entry.subtitle && <span>{entry.subtitle}</span>}
                  </div>
                )
              }
              return (
                <button key={entry.key} type="button" role="menuitem" className={['menu__item', entry.danger && 'menu__item--danger'].filter(Boolean).join(' ')} disabled={entry.disabled} tabIndex={-1} onClick={() => select(entry)}>
                  {entry.icon && <Icon name={entry.icon} size={16} />}
                  <span className="menu__item-text">{entry.label}</span>
                  {entry.hint && <span className="menu__item-hint">{entry.hint}</span>}
                </button>
              )
            })}
          </div>,
          document.body,
        )}
    </>
  )
}
