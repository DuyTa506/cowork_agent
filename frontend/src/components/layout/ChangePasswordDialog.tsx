import { useState, type FormEvent } from 'react'
import { authApi } from '../../api'
import { Alert } from '../Alert'
import { Button } from '../Button'
import { Field } from '../Field'
import { Modal } from '../Modal'
import { useToast } from '../Toast'

const MIN_LENGTH = 8

/** Lets the signed-in user change their own password (POST /api/auth/change-password). */
export function ChangePasswordDialog({ onClose }: { onClose: () => void }) {
  const notify = useToast()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const mismatch = confirm !== '' && confirm !== next
  const tooShort = next !== '' && next.length < MIN_LENGTH

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (mismatch || tooShort) return
    setBusy(true)
    setError(null)
    try {
      await authApi.changePassword(current, next)
      notify('Đã đổi mật khẩu.')
      onClose()
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Không đổi được mật khẩu.')
      setBusy(false)
    }
  }

  return (
    <Modal
      title="Đổi mật khẩu"
      onClose={onClose}
      busy={busy}
      size="sm"
      footer={
        <>
          <Button onClick={onClose} disabled={busy}>Hủy</Button>
          <Button variant="primary" type="submit" form="change-password-form" loading={busy} disabled={!current || !next || !confirm || mismatch || tooShort}>
            Đổi mật khẩu
          </Button>
        </>
      }
    >
      <form id="change-password-form" className="form" onSubmit={submit}>
        {error && <Alert kind="error">{error}</Alert>}
        <Field label="Mật khẩu hiện tại">
          {({ id }) => <input id={id} className="input" type="password" autoComplete="current-password" value={current} onChange={(event) => setCurrent(event.target.value)} required />}
        </Field>
        <Field label="Mật khẩu mới" hint={`Ít nhất ${MIN_LENGTH} ký tự.`} error={tooShort ? `Mật khẩu phải có ít nhất ${MIN_LENGTH} ký tự.` : undefined}>
          {({ id, describedBy, invalid }) => <input id={id} className="input" type="password" autoComplete="new-password" aria-describedby={describedBy} aria-invalid={invalid} value={next} onChange={(event) => setNext(event.target.value)} required />}
        </Field>
        <Field label="Nhập lại mật khẩu mới" error={mismatch ? 'Mật khẩu nhập lại chưa khớp.' : undefined}>
          {({ id, describedBy, invalid }) => <input id={id} className="input" type="password" autoComplete="new-password" aria-describedby={describedBy} aria-invalid={invalid} value={confirm} onChange={(event) => setConfirm(event.target.value)} required />}
        </Field>
      </form>
    </Modal>
  )
}
