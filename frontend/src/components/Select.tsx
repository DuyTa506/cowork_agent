import type { SelectHTMLAttributes } from 'react'

export interface SelectOption {
  value: string
  label: string
}

interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'onChange' | 'value' | 'size'> {
  value: string
  options: SelectOption[]
  onChange: (value: string) => void
  size?: 'sm' | 'md'
  invalid?: boolean
}

/** Native select with the application's styling; use `aria-label` when there is no visible label. */
export function Select({ value, options, onChange, size = 'md', invalid, className, ...rest }: SelectProps) {
  return (
    <select
      className={['select', size === 'sm' && 'select--sm', className].filter(Boolean).join(' ')}
      value={value}
      aria-invalid={invalid || rest['aria-invalid'] || undefined}
      onChange={(event) => onChange(event.target.value)}
      {...rest}
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>{option.label}</option>
      ))}
    </select>
  )
}
