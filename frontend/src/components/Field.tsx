import { useId, type ReactNode } from 'react'
import { Icon } from './Icon'

interface FieldProps {
  label: string
  hint?: ReactNode
  error?: string
  /** Marks the label with a red asterisk (also set `required` on the control). */
  required?: boolean
  /** Hide the label visually but keep it for screen readers (search boxes in toolbars). */
  hideLabel?: boolean
  className?: string
  /** Receives the id that links the label, hint and error to the control. */
  children: (ids: { id: string; describedBy: string | undefined; invalid: boolean }) => ReactNode
}

/**
 * A form control with its visible label above, optional helper text and an error message wired up for assistive technology:
 * `<Field label="Số hiệu" error={err}>{({ id, describedBy, invalid }) => <Input id={id} aria-describedby={describedBy} invalid={invalid} />}</Field>`
 */
export function Field({ label, hint, error, required, hideLabel, className, children }: FieldProps) {
  const id = useId()
  const hintId = hint ? `${id}-hint` : undefined
  const errorId = error ? `${id}-error` : undefined
  const describedBy = [hintId, errorId].filter(Boolean).join(' ') || undefined
  return (
    <div className={['field', className].filter(Boolean).join(' ')}>
      <label className={hideLabel ? 'sr-only' : 'field__label'} htmlFor={id}>
        {label}
        {required && <span className="field__req" aria-hidden="true">*</span>}
      </label>
      {children({ id, describedBy, invalid: Boolean(error) })}
      {hint && !error && <div className="field__hint" id={hintId}>{hint}</div>}
      {error && (
        <div className="field__error" id={errorId} role="alert">
          <Icon name="alertCircle" size={14} />
          <span>{error}</span>
        </div>
      )}
    </div>
  )
}
