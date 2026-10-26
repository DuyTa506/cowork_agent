import { useId, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useLayer } from '../hooks/useLayer'
import { IconButton } from './IconButton'

export interface DrawerProps {
  title: ReactNode
  /** Small line under the title (document number, unit, …). */
  subtitle?: ReactNode
  /** Chips shown under the title (state, level). */
  chips?: ReactNode
  onClose: () => void
  children: ReactNode
  /** Tab strip under the header (a `<Tabs>`); the body scrolls below it. */
  tabs?: ReactNode
  /** Sticky action row at the bottom. Put the primary action last; use `footerStart` for destructive or secondary actions. */
  footer?: ReactNode
  footerStart?: ReactNode
  /** md 520 (default), lg 640, xl 800; never wider than the screen. */
  width?: 'md' | 'lg' | 'xl'
  busy?: boolean
  /** Accessible name when `title` is not plain text. */
  label?: string
}

/**
 * Right-hand panel for the detail of a record (a document, an account, a result). Focus is trapped, Esc and a click on the
 * dimmed area close it, and focus returns to the row that opened it. Mount it to open it (`{id && <Drawer …/>}`).
 */
export function Drawer({ title, subtitle, chips, onClose, children, tabs, footer, footerStart, width = 'md', busy = false, label }: DrawerProps) {
  const titleId = useId()
  const panelRef = useRef<HTMLElement>(null)
  useLayer(panelRef, { onClose, busy })

  return createPortal(
    <div className="layer-backdrop drawer-backdrop" onMouseDown={(event) => event.target === event.currentTarget && !busy && onClose()}>
      <aside ref={panelRef} className={`drawer drawer--${width}`} role="dialog" aria-modal="true" aria-label={label} aria-labelledby={label ? undefined : titleId} tabIndex={-1}>
        <header className="drawer__head">
          <div className="drawer__heading">
            <h2 className="drawer__title" id={titleId}>{title}</h2>
            {subtitle && <p className="drawer__sub">{subtitle}</p>}
            {chips && <div className="drawer__chips">{chips}</div>}
          </div>
          <IconButton icon="close" label="Đóng" onClick={onClose} disabled={busy} />
        </header>
        {tabs && <div className="drawer__tabs">{tabs}</div>}
        <div className="drawer__body">{children}</div>
        {(footer || footerStart) && (
          <footer className="drawer__foot">
            {footerStart && <div className="drawer__foot-start">{footerStart}</div>}
            {footer}
          </footer>
        )}
      </aside>
    </div>,
    document.body,
  )
}
