import { useId, type ReactNode } from 'react'

interface SwitchProps {
  checked: boolean
  onChange: (checked: boolean) => void
  label: string
  /** Helper line under the label. */
  description?: ReactNode
  disabled?: boolean
}

/** On/off toggle with a visible label; takes effect immediately (use a Checkbox for choices that wait for a Save button). */
export function Switch({ checked, onChange, label, description, disabled }: SwitchProps) {
  const id = useId()
  return (
    <label className="switch" htmlFor={id}>
      <input id={id} type="checkbox" role="switch" checked={checked} disabled={disabled} onChange={(event) => onChange(event.target.checked)} />
      <span className="switch__track" aria-hidden="true" />
      <span className="switch__text">
        <span>{label}</span>
        {description && <span className="switch__desc">{description}</span>}
      </span>
    </label>
  )
}
