import { Children, cloneElement, isValidElement, useEffect, useId, useLayoutEffect, useRef, useState, type FocusEvent, type KeyboardEvent, type MouseEvent, type ReactElement, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

type Side = 'top' | 'bottom' | 'left' | 'right'

interface TooltipProps {
  content: ReactNode
  /** One element that can take focus (a button or link); it gets `aria-describedby` while the tip is visible. */
  children: ReactElement<Record<string, unknown>>
  side?: Side
  /** Hover delay in ms (keyboard focus shows it at once). */
  delay?: number
  /** Turn off without removing the wrapper (for example when the label is already visible). */
  disabled?: boolean
}

const GAP = 8
const MARGIN = 8

function Bubble({ anchor, side, id, children }: { anchor: HTMLElement; side: Side; id: string; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null)

  useLayoutEffect(() => {
    const bubble = ref.current
    if (!bubble) return
    const a = anchor.getBoundingClientRect()
    const b = bubble.getBoundingClientRect()
    let top = side === 'top' ? a.top - b.height - GAP : side === 'bottom' ? a.bottom + GAP : a.top + (a.height - b.height) / 2
    let left = side === 'left' ? a.left - b.width - GAP : side === 'right' ? a.right + GAP : a.left + (a.width - b.width) / 2
    // flip when there is no room on the preferred side
    if (side === 'top' && top < MARGIN) top = a.bottom + GAP
    if (side === 'bottom' && top + b.height > window.innerHeight - MARGIN) top = a.top - b.height - GAP
    left = Math.min(Math.max(MARGIN, left), window.innerWidth - b.width - MARGIN)
    top = Math.min(Math.max(MARGIN, top), window.innerHeight - b.height - MARGIN)
    setPos({ top, left })
  }, [anchor, side])

  return (
    <div ref={ref} id={id} role="tooltip" className="tooltip" style={pos ?? { top: 0, left: 0, visibility: 'hidden' }}>
      {children}
    </div>
  )
}

/**
 * Small label for icon-only controls and truncated text. Appears on hover (after `delay`) and on keyboard focus, hides on
 * blur, click, scroll or Esc. Not a place for essential information: touch users never see it.
 */
export function Tooltip({ content, children, side = 'top', delay = 450, disabled }: TooltipProps) {
  const id = useId()
  const [anchor, setAnchor] = useState<HTMLElement | null>(null)
  const timer = useRef<number | undefined>(undefined)
  const child = Children.only(children)

  const cancel = () => window.clearTimeout(timer.current)
  const hide = () => {
    cancel()
    setAnchor(null)
  }
  const show = (element: HTMLElement, wait: number) => {
    cancel()
    timer.current = window.setTimeout(() => setAnchor(element), wait)
  }

  useEffect(() => {
    if (!anchor) return
    const close = () => setAnchor(null)
    window.addEventListener('scroll', close, true)
    window.addEventListener('resize', close)
    return () => {
      window.removeEventListener('scroll', close, true)
      window.removeEventListener('resize', close)
    }
  }, [anchor])
  useEffect(() => cancel, [])

  if (!isValidElement(child) || disabled || content === null || content === undefined || content === '') return child
  const own = child.props as {
    onMouseEnter?: (event: MouseEvent<HTMLElement>) => void
    onMouseLeave?: (event: MouseEvent<HTMLElement>) => void
    onFocus?: (event: FocusEvent<HTMLElement>) => void
    onBlur?: (event: FocusEvent<HTMLElement>) => void
    onKeyDown?: (event: KeyboardEvent<HTMLElement>) => void
    onClick?: (event: MouseEvent<HTMLElement>) => void
    'aria-describedby'?: string
  }

  return (
    <>
      {cloneElement(child, {
        'aria-describedby': anchor ? [own['aria-describedby'], id].filter(Boolean).join(' ') : own['aria-describedby'],
        onMouseEnter: (event: MouseEvent<HTMLElement>) => {
          own.onMouseEnter?.(event)
          show(event.currentTarget, delay)
        },
        onMouseLeave: (event: MouseEvent<HTMLElement>) => {
          own.onMouseLeave?.(event)
          hide()
        },
        onFocus: (event: FocusEvent<HTMLElement>) => {
          own.onFocus?.(event)
          if (event.currentTarget.matches(':focus-visible')) show(event.currentTarget, 0)
        },
        onBlur: (event: FocusEvent<HTMLElement>) => {
          own.onBlur?.(event)
          hide()
        },
        onClick: (event: MouseEvent<HTMLElement>) => {
          own.onClick?.(event)
          hide()
        },
        onKeyDown: (event: KeyboardEvent<HTMLElement>) => {
          own.onKeyDown?.(event)
          if (event.key === 'Escape') hide()
        },
      })}
      {anchor && createPortal(<Bubble anchor={anchor} side={side} id={id}>{content}</Bubble>, document.body)}
    </>
  )
}
