import { useState, type FormEvent } from 'react'
import { adminApi, type Role, type User, type UserUpdate } from '../../api'
import { ROLES, ROLE_LABELS } from '../../lib/labels'
import { Alert } from '../Alert'
import { Button } from '../Button'
import { Field } from '../Field'
import { Modal } from '../Modal'
import { Select } from '../Select'
import { Switch } from '../Switch'
import { useToast } from '../Toast'
import { UnitSelect } from '../UnitSelect'

const MIN_PASSWORD = 8
const ROLE_OPTIONS = ROLES.map((role) => ({ value: role, label: ROLE_LABELS[role] }))

interface UserDialogProps {
  /** The account to edit; omit to create a new one. */
  user?: User
  onClose: () => void
  onSaved: () => void
}

/** Create or edit an account: name, unit, role, activation and (re)setting the password. */
export function UserDialog({ user, onClose, onSaved }: UserDialogProps) {
  const notify = useToast()
  const [username, setUsername] = useState('')
  const [fullName, setFullName] = useState(user?.full_name ?? '')
  const [unitId, setUnitId] = useState(user?.unit_id ?? '')
  const [role, setRole] = useState<Role>(user?.role ?? 'staff')
  const [active, setActive] = useState(user?.is_active ?? true)
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const passwordTooShort = password !== '' && password.length < MIN_PASSWORD
  const canSubmit = unitId !== '' && !passwordTooShort && (user ? true : username.trim() !== '' && password !== '')

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!canSubmit) return
    setBusy(true)
    setError(null)
    try {
      if (user) {
        const changes: UserUpdate = {}
        if (fullName !== user.full_name) changes.full_name = fullName
        if (unitId !== user.unit_id) changes.unit_id = unitId
        if (role !== user.role) changes.role = role
        if (active !== user.is_active) changes.is_active = active
        if (password) changes.password = password
        if (Object.keys(changes).length > 0) await adminApi.updateUser(user.id, changes)
        notify('Đã cập nhật tài khoản.')
      } else {
        await adminApi.createUser({ username: username.trim(), password, full_name: fullName, unit_id: unitId, role })
        notify('Đã tạo tài khoản.')
      }
      onSaved()
      onClose()
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Không lưu được tài khoản.')
      setBusy(false)
    }
  }

  return (
    <Modal
      title={user ? `Sửa tài khoản ${user.username}` : 'Thêm tài khoản'}
      onClose={onClose}
      busy={busy}
      footer={
        <>
          <Button onClick={onClose} disabled={busy}>Hủy</Button>
          <Button variant="primary" type="submit" form="user-form" loading={busy} disabled={!canSubmit}>
            {user ? 'Lưu' : 'Tạo tài khoản'}
          </Button>
        </>
      }
    >
      <form id="user-form" className="form" onSubmit={submit}>
        {error && <Alert kind="error">{error}</Alert>}
        {!user && (
          <Field label="Tên đăng nhập" hint="Không có khoảng trắng; không đổi được sau khi tạo.">
            {({ id, describedBy }) => <input id={id} className="input" autoComplete="off" aria-describedby={describedBy} value={username} onChange={(event) => setUsername(event.target.value)} required />}
          </Field>
        )}
        <Field label="Họ và tên">
          {({ id }) => <input id={id} className="input" autoComplete="off" value={fullName} onChange={(event) => setFullName(event.target.value)} />}
        </Field>
        <Field label="Đơn vị" hint="Tài khoản xem được văn bản của đơn vị này và các đơn vị cấp dưới.">
          {({ id, describedBy }) => <UnitSelect id={id} aria-describedby={describedBy} value={unitId} emptyLabel="Chọn đơn vị" onChange={setUnitId} />}
        </Field>
        <Field label="Vai trò" hint="Chỉ huy xem được văn bản mật; quản trị viên không xem văn bản mật.">
          {({ id, describedBy }) => <Select id={id} aria-describedby={describedBy} value={role} options={ROLE_OPTIONS} onChange={(value) => setRole(value as Role)} />}
        </Field>
        {user && <Switch checked={active} onChange={setActive} label={active ? 'Tài khoản đang hoạt động' : 'Tài khoản bị khóa, không đăng nhập được'} />}
        <Field
          label={user ? 'Đặt lại mật khẩu' : 'Mật khẩu'}
          hint={user ? `Để trống nếu không đổi. Tối thiểu ${MIN_PASSWORD} ký tự.` : `Tối thiểu ${MIN_PASSWORD} ký tự.`}
          error={passwordTooShort ? `Mật khẩu phải có ít nhất ${MIN_PASSWORD} ký tự.` : undefined}
        >
          {({ id, describedBy, invalid }) => (
            <input id={id} className="input" type="password" autoComplete="new-password" aria-describedby={describedBy} aria-invalid={invalid} value={password} onChange={(event) => setPassword(event.target.value)} required={!user} />
          )}
        </Field>
      </form>
    </Modal>
  )
}
