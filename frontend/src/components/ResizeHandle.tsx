import { useRef, useState } from 'react'
import type { KeyboardEvent, PointerEvent } from 'react'
import type { ResizableWidth } from '../hooks/useResizableWidth'

interface ResizeHandleProps {
  size: ResizableWidth
  /** Which edge of the panel the handle sits on: dragging a "right" edge to the right widens it; a "left" edge, the opposite. */
  edge: 'left' | 'right'
  label: string
}

const STEP = 16

/** A thin draggable divider on one edge of a panel (pointer or arrow keys; double-click restores the default width). */
export function ResizeHandle({ size, edge, label }: ResizeHandleProps) {
  const start = useRef<{ x: number; width: number } | null>(null)
  const [dragging, setDragging] = useState(false)
  const sign = edge === 'right' ? 1 : -1

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return
    event.currentTarget.setPointerCapture(event.pointerId)
    start.current = { x: event.clientX, width: size.width }
    setDragging(true)
    document.body.classList.add('is-resizing')
  }
  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (!start.current) return
    size.set(start.current.width + sign * (event.clientX - start.current.x))
  }
  const end = (event: PointerEvent<HTMLDivElement>) => {
    if (!start.current) return
    start.current = null
    setDragging(false)
    document.body.classList.remove('is-resizing')
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
  }
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const move = event.key === 'ArrowRight' ? STEP : event.key === 'ArrowLeft' ? -STEP : 0
    if (event.key === 'Home') size.set(size.min)
    else if (event.key === 'End') size.set(size.max)
    else if (move) size.set(size.width + sign * move)
    else return
    event.preventDefault()
  }

  return (
    <div
      className={['resizer', `resizer--${edge}`, dragging && 'resizer--on'].filter(Boolean).join(' ')}
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-valuemin={size.min}
      aria-valuemax={size.max}
      aria-valuenow={size.width}
      tabIndex={0}
      title="Kéo để đổi độ rộng · nhấp đúp để về mặc định"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={end}
      onPointerCancel={end}
      onDoubleClick={size.reset}
      onKeyDown={onKeyDown}
    />
  )
}
