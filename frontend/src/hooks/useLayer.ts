import { useEffect, useRef, type RefObject } from 'react'

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

/** Open layers (modal, drawer, palette), innermost last: only the innermost one reacts to the keyboard. */
const openLayers: symbol[] = []

interface LayerOptions {
  onClose: () => void
  /** While true Esc does nothing (a request is running). */
  busy?: boolean
  /** Turn the behaviour on and off for a panel that stays mounted (the mobile sidebar). Default true. */
  enabled?: boolean
}

/**
 * Behaviour shared by dialogs and drawers: focus moves in on open (first `[data-autofocus]`, else the first field, else the
 * panel itself) and returns to the opener on close; Tab stays inside; Esc closes the innermost layer. Keys are handled on
 * the document so they still work after the focused button was removed.
 */
export function useLayer(ref: RefObject<HTMLElement | null>, { onClose, busy = false, enabled = true }: LayerOptions): void {
  const latest = useRef({ onClose, busy })
  useEffect(() => {
    latest.current = { onClose, busy }
  })

  useEffect(() => {
    if (!enabled) return
    const id = Symbol('layer')
    openLayers.push(id)
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const panel = ref.current
    const target =
      panel?.querySelector<HTMLElement>('[data-autofocus]') ?? panel?.querySelector<HTMLElement>('input, select, textarea') ?? panel
    target?.focus({ preventScroll: true })

    const onKeyDown = (event: KeyboardEvent) => {
      if (openLayers[openLayers.length - 1] !== id || !panel) return
      if (event.key === 'Escape') {
        if (!latest.current.busy) {
          event.preventDefault()
          latest.current.onClose()
        }
        return
      }
      if (event.key !== 'Tab') return
      const items = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((item) => item.offsetParent !== null || item === document.activeElement)
      const first = items[0]
      const last = items[items.length - 1]
      if (!first || !last) {
        event.preventDefault()
        return
      }
      const active = document.activeElement
      if (!panel.contains(active)) {
        event.preventDefault()
        first.focus()
      } else if (event.shiftKey && (active === first || active === panel)) {
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
      openLayers.splice(openLayers.indexOf(id), 1)
      if (opener?.isConnected) opener.focus({ preventScroll: true })
    }
    // The panel element is stable for the layer's lifetime.
  }, [ref, enabled])
}
