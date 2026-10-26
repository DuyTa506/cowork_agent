import { useId, useState, type FormEvent, type ReactNode } from 'react'
import { documentsApi, type DocumentDetail, type MetadataUpdate } from '../../api'
import { missingFields } from '../../lib/documents'
import { formatDate } from '../../lib/format'
import { DOCUMENT_TYPES } from '../../lib/labels'
import { Button } from '../Button'
import { LevelChip } from '../Chip'
import { DateInput } from '../DateInput'
import { Icon } from '../Icon'
import { useToast } from '../Toast'
import { Callout } from './Callout'

type EditableKey = keyof MetadataUpdate

interface FieldSpec {
  key: EditableKey
  label: string
  required?: boolean
  /** Occupies the full row (otherwise half of it). */
  wide?: boolean
  multiline?: boolean
}

const GROUPS: { title: string; fields: FieldSpec[] }[] = [
  {
    title: 'Nhận dạng',
    fields: [
      { key: 'subject', label: 'Trích yếu', required: true, wide: true, multiline: true },
      { key: 'title', label: 'Tiêu đề', wide: true },
      { key: 'document_type', label: 'Loại văn bản', required: true, wide: true },
      { key: 'document_number', label: 'Số' },
      { key: 'symbol', label: 'Ký hiệu' },
    ],
  },
  {
    title: 'Ban hành',
    fields: [
      { key: 'issuer', label: 'Cơ quan ban hành', wide: true },
      { key: 'issued_date', label: 'Ngày ban hành', required: true },
      { key: 'signer', label: 'Người ký' },
    ],
  },
]

const ALL_FIELDS = GROUPS.flatMap((group) => group.fields)

interface MetadataFormProps {
  document: DocumentDetail
  onSaved: (document: DocumentDetail) => void
  /** Read-only groups rendered after the editable ones (inside the form, so the save bar stays in reach). */
  children?: ReactNode
}

/**
 * Extracted fields, grouped (Nhận dạng, Ban hành), editable by the uploader or an administrator. Missing required fields get
 * a red border, an inline message and a warning callout; only changed fields are sent; an invalid date blocks saving.
 */
export function MetadataForm({ document, onSaved, children }: MetadataFormProps) {
  const notify = useToast()
  const [values, setValues] = useState<Record<EditableKey, string>>(() => pick(document))
  const [dateValid, setDateValid] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const editable = document.can_manage
  const missing = missingFields(values)
  const changes = ALL_FIELDS.filter(({ key }) => values[key] !== document[key]).reduce<MetadataUpdate>(
    (patch, { key }) => ({ ...patch, [key]: values[key].trim() }),
    {},
  )
  const dirty = Object.keys(changes).length > 0
  const missingLabels = ALL_FIELDS.filter(({ key }) => missing.includes(key)).map(({ label }) => label)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!dirty || !dateValid) return
    setBusy(true)
    setError(null)
    try {
      onSaved(await documentsApi.updateDocument(document.id, changes))
      notify('Đã lưu thông tin văn bản.')
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Không lưu được thông tin.')
    } finally {
      setBusy(false)
    }
  }

  const reset = () => {
    setValues(pick(document))
    setDateValid(true)
    setError(null)
  }

  return (
    <form className="dform" onSubmit={submit} noValidate>
      {editable && missingLabels.length > 0 && (
        <Callout tone="warning" title={`Còn thiếu ${missingLabels.length} trường bắt buộc`}>
          {missingLabels.join(', ')}. Các ô viền đỏ bên dưới cần nhập tay để hoàn tất hồ sơ.
        </Callout>
      )}
      {error && <Callout tone="danger" title="Không lưu được">{error}</Callout>}

      <p className="dform__caption">Trường đã trích xuất</p>
      {GROUPS.map((group) => (
        <section key={group.title} className="dgroup" aria-label={group.title}>
          <h3 className="dgroup__title section-label">{group.title}</h3>
          <div className="dgroup__grid">
            {group.fields.map((field) => (
              <FieldRow
                key={field.key}
                spec={field}
                value={values[field.key]}
                editable={editable}
                missing={editable && missing.includes(field.key)}
                dateInvalid={field.key === 'issued_date' && !dateValid}
                onChange={(next) => setValues((current) => ({ ...current, [field.key]: next }))}
                onDateValidity={setDateValid}
              />
            ))}
            {group.title === 'Ban hành' && (
              <>
                <ReadRow label="Đơn vị" value={document.unit_name || document.unit_id || '—'} />
                <ReadRow label="Mức độ" value={<LevelChip level={document.level} />} />
              </>
            )}
          </div>
        </section>
      ))}

      <datalist id="document-type-options">
        {DOCUMENT_TYPES.map((type) => <option key={type} value={type} />)}
      </datalist>

      {children}

      {!editable && (
        <p className="dform__locked"><Icon name="lock" size={16} /> Chỉ người tải lên hoặc quản trị viên được sửa thông tin này.</p>
      )}

      {editable && dirty && (
        <div className="dform__bar" role="group" aria-label="Lưu thay đổi">
          <span className="dform__bar-text">{dateValid ? 'Có thay đổi chưa lưu' : 'Ngày ban hành chưa hợp lệ'}</span>
          <Button onClick={reset} disabled={busy}>Hoàn tác</Button>
          <Button variant="primary" type="submit" icon="save" loading={busy} disabled={!dateValid}>Lưu thay đổi</Button>
        </div>
      )}
    </form>
  )
}

interface FieldRowProps {
  spec: FieldSpec
  value: string
  editable: boolean
  missing: boolean
  dateInvalid: boolean
  onChange: (value: string) => void
  onDateValidity: (valid: boolean) => void
}

function FieldRow({ spec, value, editable, missing, dateInvalid, onChange, onDateValidity }: FieldRowProps) {
  const id = useId()
  const errorId = `${id}-error`
  const className = spec.wide ? 'dfield dfield--wide' : 'dfield'
  if (!editable) {
    const text = spec.key === 'issued_date' ? formatDate(value) : value
    return <ReadRow label={spec.label} value={text || '—'} wide={spec.wide} />
  }
  const invalid = missing || dateInvalid
  const message = dateInvalid ? 'Ngày không hợp lệ, nhập theo dd/mm/yyyy.' : missing ? 'Còn thiếu, cần nhập tay.' : ''
  return (
    <div className={className}>
      <label className="dfield__label" htmlFor={id}>
        {spec.label}
        {spec.required && <span className="dfield__req" aria-hidden="true"> *</span>}
      </label>
      {spec.key === 'issued_date' ? (
        <DateInput id={id} value={value} aria-describedby={message ? errorId : undefined} aria-invalid={invalid || undefined} className={invalid ? 'input--need' : undefined} onChange={onChange} onValidityChange={onDateValidity} />
      ) : spec.multiline ? (
        <textarea
          id={id}
          rows={3}
          className={invalid ? 'input input--need dfield__area' : 'input dfield__area'}
          value={value}
          aria-describedby={message ? errorId : undefined}
          aria-invalid={invalid || undefined}
          onChange={(event) => onChange(event.target.value)}
        />
      ) : (
        <input
          id={id}
          className={invalid ? 'input input--need' : 'input'}
          value={value}
          aria-describedby={message ? errorId : undefined}
          aria-invalid={invalid || undefined}
          list={spec.key === 'document_type' ? 'document-type-options' : undefined}
          onChange={(event) => onChange(event.target.value)}
        />
      )}
      {message && <p className="dfield__error" id={errorId}><Icon name="alertCircle" size={16} weight="fill" /> {message}</p>}
    </div>
  )
}

function ReadRow({ label, value, wide }: { label: string; value: ReactNode; wide?: boolean }) {
  return (
    <div className={wide ? 'dfield dfield--wide dfield--read' : 'dfield dfield--read'}>
      <span className="dfield__label">{label}</span>
      <div className="dfield__value">{value}</div>
    </div>
  )
}

export { ReadRow }

function pick(document: DocumentDetail): Record<EditableKey, string> {
  return {
    title: document.title,
    subject: document.subject,
    document_type: document.document_type,
    document_number: document.document_number,
    symbol: document.symbol,
    issuer: document.issuer,
    issued_date: document.issued_date,
    signer: document.signer,
  }
}
