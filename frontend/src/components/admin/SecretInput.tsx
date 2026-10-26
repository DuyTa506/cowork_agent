import { Button } from '../Button'
import { Field } from '../Field'
import { Icon } from '../Icon'
import type { SecretDraft } from '../../lib/settings'

interface SecretInputProps {
  label: string
  hint?: string
  /** Whether the server already holds a value. */
  isSet: boolean
  draft: SecretDraft
  onChange: (draft: SecretDraft) => void
}

/**
 * Input for a secret such as an API key. The saved value is never shown: a stored key reads "Đã đặt" with "Đổi" and "Xóa",
 * which map to sending the new text, or an empty string, on save; untouched means the server keeps it.
 */
export function SecretInput({ label, hint, isSet, draft, onChange }: SecretInputProps) {
  if (draft.mode === 'keep') {
    return (
      <div className="field">
        <span className="field__label">{label}</span>
        <div className="secret">
          <span className="secret__state"><Icon name="checkCircle" size={18} weight="fill" />Đã đặt<span className="secret__mask" aria-hidden="true">••••••••••</span></span>
          <Button onClick={() => onChange({ mode: 'change', text: '' })} aria-label={`Đổi ${label}`}>Đổi</Button>
          <Button variant="danger" onClick={() => onChange({ mode: 'clear', text: '' })} aria-label={`Xóa ${label}`}>Xóa</Button>
        </div>
        {hint && <div className="field__hint">{hint}</div>}
      </div>
    )
  }
  if (draft.mode === 'clear') {
    return (
      <div className="field">
        <span className="field__label">{label}</span>
        <div className="secret">
          <span className="secret__state secret__state--warn"><Icon name="alert" size={18} weight="fill" />Sẽ bị xóa khi lưu</span>
          <Button onClick={() => onChange({ mode: 'keep', text: '' })}>Hoàn tác</Button>
        </div>
      </div>
    )
  }
  return (
    <Field label={label} hint={hint}>
      {({ id, describedBy }) => (
        <div className="secret">
          <input
            id={id}
            className="input"
            type="password"
            autoComplete="new-password"
            aria-describedby={describedBy}
            placeholder={isSet ? 'Nhập giá trị mới' : 'Chưa đặt'}
            value={draft.text}
            onChange={(event) => onChange({ mode: 'change', text: event.target.value })}
          />
          {isSet && <Button onClick={() => onChange({ mode: 'keep', text: '' })}>Giữ nguyên</Button>}
        </div>
      )}
    </Field>
  )
}
