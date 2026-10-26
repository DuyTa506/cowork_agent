import { useState } from 'react'
import { formatDate, parseDate } from '../lib/format'

interface DateInputProps {
  /** ISO `yyyy-mm-dd`, or empty. */
  value: string
  /** Called with an ISO date, or an empty string when cleared. Not called while the text is not a valid date. */
  onChange: (iso: string) => void
  id?: string
  className?: string
  'aria-label'?: string
  'aria-describedby'?: string
  'aria-invalid'?: boolean
  disabled?: boolean
  /** Reports whether the text currently typed is a valid date (or empty). */
  onValidityChange?: (valid: boolean) => void
}

/** Text input that shows and accepts dd/mm/yyyy regardless of the browser's locale, and works in ISO dates. */
export function DateInput({ value, onChange, className, onValidityChange, ...rest }: DateInputProps) {
  const [draft, setDraft] = useState(formatDate(value, ''))
  const [lastValue, setLastValue] = useState(value)
  const [invalid, setInvalid] = useState(false)

  if (value !== lastValue) {
    // The parent changed the value (reset, other document): show it.
    setLastValue(value)
    setDraft(formatDate(value, ''))
    setInvalid(false)
  }

  const update = (text: string) => {
    setDraft(text)
    const trimmed = text.trim()
    if (trimmed === '') {
      setInvalid(false)
      onValidityChange?.(true)
      setLastValue('')
      onChange('')
      return
    }
    const iso = parseDate(trimmed)
    setInvalid(iso === null)
    onValidityChange?.(iso !== null)
    if (iso !== null) {
      setLastValue(iso)
      onChange(iso)
    }
  }

  return (
    <input
      {...rest}
      type="text"
      inputMode="numeric"
      autoComplete="off"
      placeholder="dd/mm/yyyy"
      maxLength={10}
      value={draft}
      aria-invalid={rest['aria-invalid'] || invalid || undefined}
      className={['input', className, invalid && 'input--need'].filter(Boolean).join(' ')}
      onChange={(event) => update(event.target.value)}
    />
  )
}
