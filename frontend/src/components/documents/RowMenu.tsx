import { useEffect, useId, useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Icon, type IconName } from '../Icon'

export interface MenuAction {
  key: string
  label: string
  icon: IconName
  danger?: boolean
  onSelect: () => void
  /** A hairline above this item. */
  separated?: boolean
}

interface RowMenuProps {
  label: string
  actions: MenuAction[]
}

const MENU_WIDTH = 220

/** Kebab button with a popup menu (portal, flips upward near the bottom edge, arrow keys, Esc, click outside). */
export function RowMenu({ label, actions }: RowMenuProps) {
  const [open, setOpen] = useState(false)
  const [position, setPosition] = useState<{ top: number; left: number } | null>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const menuId = useId()

  useLayoutEffect(() => {
    if (!open) {
      setPosition(null)
      return
    }
    if (!buttonRef.current) return
    const rect = buttonRef.current.getBoundingClientRect()
    const height = actions.length * 38 + 12
    const top = rect.bottom + 4 + height > window.innerHeight ? Math.max(8, rect.top - 4 - height) : rect.bottom + 4
    setPosition({ top, left: Math.max(8, Math.min(rect.right - MENU_WIDTH, window.innerWidth - MENU_WIDTH - 8)) })
  }, [open, actions.length])

  useEffect(() => {
    if (!open) return
    const close = () => setOpen(false)
    const onPointer = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node) && !buttonRef.current?.contains(event.target as Node)) close()
    }
    document.addEventListener('mousedown', onPointer)
    window.addEventListener('resize', close)
    window.addEventListener('scroll', close, true)
    return () => {
      document.removeEventListener('mousedown', onPointer)
      window.removeEventListener('resize', close)
      window.removeEventListener('scroll', close, true)
    }
  }, [open])

  // Focus the first item once the menu is placed (a hidden menu cannot take focus).
  useEffect(() => {
    if (open && position) menuRef.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus()
  }, [open, position])

  const onMenuKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const items = Array.from(menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [])
    const index = items.indexOf(document.activeElement as HTMLElement)
    if (event.key === 'Escape') {
      event.preventDefault()
      event.stopPropagation()
      setOpen(false)
      buttonRef.current?.focus()
    } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      items[(index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length]?.focus()
    } else if (event.key === 'Home' || event.key === 'End') {
      event.preventDefault()
      items[event.key === 'Home' ? 0 : items.length - 1]?.focus()
    } else if (event.key === 'Tab') {
      setOpen(false)
    }
  }

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        className={open ? 'kebab is-open' : 'kebab'}
        aria-label={label}
        title="Thao tác"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={(event) => { event.stopPropagation(); setOpen((value) => !value) }}
        onKeyDown={(event) => {
          event.stopPropagation()
          if (event.key === 'ArrowDown' && !open) { event.preventDefault(); setOpen(true) }
        }}
      >
        <Icon name="moreVertical" size={20} />
      </button>
      {open &&
        createPortal(
          <div
            ref={menuRef}
            id={menuId}
            className="menu"
            role="menu"
            aria-label={label}
            style={{ top: position?.top ?? 0, left: position?.left ?? 0, width: MENU_WIDTH, visibility: position ? 'visible' : 'hidden' }}
            onKeyDown={onMenuKey}
            onClick={(event) => event.stopPropagation()}
          >
            {actions.map((action) => (
              <MenuItem key={action.key} action={action} onDone={() => { setOpen(false); action.onSelect() }} />
            ))}
          </div>,
          document.body,
        )}
    </>
  )
}

function MenuItem({ action, onDone }: { action: MenuAction; onDone: () => void }): ReactNode {
  return (
    <>
      {action.separated && <div className="menu__sep" role="separator" />}
      <button type="button" role="menuitem" className={action.danger ? 'menu__item menu__item--danger' : 'menu__item'} onClick={onDone}>
        <Icon name={action.icon} size={18} />
        {action.label}
      </button>
    </>
  )
}
