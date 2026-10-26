import { useId, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useLayer } from '../hooks/useLayer'
import { IconButton } from './IconButton'

export interface ModalProps {
  title: string
  /** One line under the title. */
  description?: ReactNode
  onClose: () => void
  children: ReactNode
  /** Buttons row at the bottom (primary action last, on the right). */
  footer?: ReactNode
  /** Width: sm 440, md 480 (default), lg 640, xl 800. On phones every size becomes a bottom sheet. */
  size?: 'sm' | 'md' | 'lg' | 'xl'
  /** While true the dialog cannot be dismissed (a request is running). */
  busy?: boolean
  /** `alertdialog` for confirmations that interrupt the user. */
  role?: 'dialog' | 'alertdialog'
}

/**
 * Modal dialog for short decisions and small forms (up to about five fields). Rendered in a portal: Esc closes it, Tab stays
 * inside, focus moves in on open (use `data-autofocus` to choose the control) and returns to the opener on close.
 * Mount it to open it (`{open && <Modal …/>}`). Use a Drawer for anything that shows a record's details.
 */
export function Modal({ title, description, onClose, children, footer, size = 'md', busy = false, role = 'dialog' }: ModalProps) {
  const titleId = useId()
  const descId = useId()
  const dialogRef = useRef<HTMLDivElement>(null)
  useLayer(dialogRef, { onClose, busy })

  return createPortal(
    <div className="layer-backdrop modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && !busy && onClose()}>
      <div
        ref={dialogRef}
        className={`modal modal--${size}`}
        role={role}
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descId : undefined}
        tabIndex={-1}
      >
        <header className="modal__head">
          <div className="modal__heading">
            <h2 className="modal__title" id={titleId}>{title}</h2>
            {description && <p className="modal__desc" id={descId}>{description}</p>}
          </div>
          <IconButton icon="close" label="Đóng" size="sm" onClick={onClose} disabled={busy} />
        </header>
        <div className="modal__body">{children}</div>
        {footer && <footer className="modal__foot">{footer}</footer>}
      </div>
    </div>,
    document.body,
  )
}
