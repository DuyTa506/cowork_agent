import { useEffect, useRef, type ReactNode } from 'react'

interface CheckboxProps {
  checked: boolean
  onChange: (checked: boolean) => void
  /** Visible label. Without one, pass `aria-label` (table selection columns). */
  label?: ReactNode
  description?: ReactNode
  /** Partly selected (the "select all" box when only some rows are ticked). */
  indeterminate?: boolean
  disabled?: boolean
  id?: string
  'aria-label'?: string
  className?: string
}

/** Checkbox with an optional label and description. */
export function Checkbox({ checked, onChange, label, description, indeterminate = false, disabled, id, className, ...rest }: CheckboxProps) {
  const ref = useRef<HTMLInputElement>(null)
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate
  }, [indeterminate])
  const box = (
    <input
      ref={ref}
      id={id}
      type="checkbox"
      className="checkbox"
      checked={checked}
      disabled={disabled}
      aria-label={rest['aria-label']}
      onChange={(event) => onChange(event.target.checked)}
    />
  )
  if (!label) return box
  return (
    <label className={['choice', disabled && 'choice--disabled', className].filter(Boolean).join(' ')}>
      {box}
      <span className="choice__text">
        <span>{label}</span>
        {description && <span className="choice__desc">{description}</span>}
      </span>
    </label>
  )
}
