import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Icon, type IconName } from './Icon'
import { IconButton } from './IconButton'

export type ToastKind = 'success' | 'error' | 'info' | 'warning'

export interface ToastOptions {
  /** Button inside the toast ("Hoàn tác", "Thử lại"). Errors keep their action for 8 s. */
  action?: { label: string; onClick: () => void }
  /** Milliseconds; default 4000 (errors 8000). */
  duration?: number
}

interface ToastItem {
  id: number
  kind: ToastKind
  message: string
  options: ToastOptions
}

type Notify = (message: string, kind?: ToastKind, options?: ToastOptions) => void

const ToastContext = createContext<Notify | null>(null)

const ICONS: Record<ToastKind, IconName> = { success: 'checkCircle', error: 'alertCircle', info: 'info', warning: 'alert' }

/** One toast; the timer pauses while the pointer is over it or focus is inside. */
function ToastView({ item, onDismiss }: { item: ToastItem; onDismiss: (id: number) => void }) {
  const [paused, setPaused] = useState(false)
  const duration = item.options.duration ?? (item.kind === 'error' ? 8000 : 4000)
  const remaining = useRef(duration)
  useEffect(() => {
    if (paused) return
    const started = Date.now()
    const timer = window.setTimeout(() => onDismiss(item.id), remaining.current)
    return () => {
      window.clearTimeout(timer)
      remaining.current -= Date.now() - started
    }
  }, [paused, item.id, onDismiss])
  const { action } = item.options
  return (
    <div
      className={`toast toast--${item.kind}`}
      role={item.kind === 'error' ? 'alert' : 'status'}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
    >
      <Icon name={ICONS[item.kind]} size={18} className="toast__icon" />
      <div className="toast__body">
        <span>{item.message}</span>
        {action && (
          <button type="button" className="toast__action" onClick={() => { action.onClick(); onDismiss(item.id) }}>{action.label}</button>
        )}
      </div>
      <IconButton icon="close" label="Đóng thông báo" size="sm" tooltip={false} className="toast__close" onClick={() => onDismiss(item.id)} />
    </div>
  )
}

/** Shows short notifications bottom-right and announces them to screen readers. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const nextId = useRef(1)

  const dismiss = useCallback((id: number) => setItems((current) => current.filter((item) => item.id !== id)), [])
  const notify = useCallback<Notify>((message, kind = 'success', options = {}) => {
    const id = nextId.current++
    setItems((current) => [...current.slice(-3), { id, kind, message, options }])
  }, [])
  const value = useMemo(() => notify, [notify])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toasts" aria-live="polite">
        {items.map((item) => (
          <ToastView key={item.id} item={item} onDismiss={dismiss} />
        ))}
      </div>
    </ToastContext.Provider>
  )
}

/** Returns `notify(message, kind?, options?)`; must be used under `ToastProvider`. */
export function useToast(): Notify {
  const notify = useContext(ToastContext)
  if (!notify) throw new Error('useToast must be used inside ToastProvider')
  return notify
}
