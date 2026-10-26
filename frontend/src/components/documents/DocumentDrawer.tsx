import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { createPortal } from 'react-dom'
import { useResizableWidth } from '../../hooks/useResizableWidth'
import { ResizeHandle } from '../ResizeHandle'
import { DocumentDetailPanel } from './DocumentDetailPanel'

interface DocumentDrawerProps {
  documentId: number
  onClose: () => void
  onOpenPage: () => void
  onChanged: () => void
  onDeleted: () => void
  tagSuggestions?: string[]
}

const DEFAULT_WIDTH = 520
const MIN_WIDTH = 400
const MARGIN = 72 // some of the list always stays visible beside the drawer

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

/**
 * Right-hand drawer (its width can be dragged by the left edge or set with the arrow keys, and is remembered; a full-width sheet on
 * narrow screens) over a light scrim. Esc and a click on the scrim close it,
 * Tab stays inside, and focus returns to the row that opened it.
 */
export function DocumentDrawer({ documentId, onClose, onOpenPage, onChanged, onDeleted, tagSuggestions }: DocumentDrawerProps) {
  const drawerRef = useRef<HTMLElement>(null)
  const [screen, setScreen] = useState(window.innerWidth)
  const size = useResizableWidth('qk3.drawer.width', DEFAULT_WIDTH, MIN_WIDTH, Math.max(MIN_WIDTH, screen - MARGIN))
  useEffect(() => {
    const onResize = () => setScreen(window.innerWidth)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])
  const closeRef = useRef(onClose)
  useEffect(() => {
    closeRef.current = onClose
  })

  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const drawer = drawerRef.current
    drawer?.focus()

    const onKeyDown = (event: KeyboardEvent) => {
      if (!drawer) return
      // A confirmation dialog on top of the drawer handles the keyboard itself.
      if (document.querySelector('.modal-backdrop')) return
      if (event.key === 'Escape') {
        closeRef.current()
        return
      }
      if (event.key !== 'Tab') return
      const items = Array.from(drawer.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((item) => item.offsetParent !== null)
      const first = items[0]
      const last = items[items.length - 1]
      if (!first || !last) return
      const active = document.activeElement
      if (!drawer.contains(active)) {
        event.preventDefault()
        first.focus()
      } else if (event.shiftKey && (active === first || active === drawer)) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && active === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      const target = opener?.isConnected ? opener : document.querySelector<HTMLElement>(`[data-doc-id="${documentId}"]`)
      target?.focus()
    }
    // Focus handling belongs to the first render for this document only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return createPortal(
    <div className="drawer-scrim" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <aside ref={drawerRef} className="drawer" style={{ '--drawer-w': `${size.width}px` } as CSSProperties} role="dialog" aria-modal="true" aria-label="Chi tiết văn bản" tabIndex={-1}>
        <ResizeHandle size={size} edge="left" label="Đổi độ rộng khung chi tiết" />
        <DocumentDetailPanel
          documentId={documentId}
          variant="drawer"
          onClose={onClose}
          onOpenPage={onOpenPage}
          onChanged={onChanged}
          onDeleted={onDeleted}
          tagSuggestions={tagSuggestions}
        />
      </aside>
    </div>,
    document.body,
  )
}
