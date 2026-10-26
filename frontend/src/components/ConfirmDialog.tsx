import { useState, type ReactNode } from 'react'
import { Alert } from './Alert'
import { Button } from './Button'
import { Modal } from './Modal'

interface ConfirmDialogProps {
  title: string
  children: ReactNode
  confirmLabel: string
  cancelLabel?: string
  /** Destructive action: the confirm button is red. Name the object in `title` or the text ("Xóa văn bản 12/QĐ-BTL?"). */
  danger?: boolean
  /** May be async; the dialog stays open and busy until it settles. A thrown error is shown in the dialog. */
  onConfirm: () => void | Promise<void>
  onCancel: () => void
}

/** Asks the user to confirm an action before it runs. Focus starts on "Hủy" so Enter never deletes by accident. */
export function ConfirmDialog({ title, children, confirmLabel, cancelLabel = 'Hủy', danger = false, onConfirm, onCancel }: ConfirmDialogProps) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const confirm = async () => {
    setBusy(true)
    setError(null)
    try {
      await onConfirm()
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Thao tác thất bại.')
      setBusy(false)
    }
  }

  return (
    <Modal
      title={title}
      onClose={onCancel}
      busy={busy}
      size="sm"
      role="alertdialog"
      footer={
        <>
          <Button onClick={onCancel} disabled={busy} data-autofocus>{cancelLabel}</Button>
          <Button variant={danger ? 'danger-solid' : 'primary'} onClick={confirm} loading={busy}>{confirmLabel}</Button>
        </>
      }
    >
      {children}
      {error && <Alert kind="error">{error}</Alert>}
    </Modal>
  )
}
