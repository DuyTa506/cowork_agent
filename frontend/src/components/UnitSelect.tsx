import type { SelectHTMLAttributes } from 'react'
import { useUnits } from '../hooks/useUnits'

interface UnitSelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'onChange' | 'value'> {
  value: string
  onChange: (unitId: string) => void
  /** Label of the empty choice (for example "Tất cả đơn vị"); omit when a unit is mandatory. */
  emptyLabel?: string
}

const INDENT = '   '

/** The organisation chart as an indented select, so the hierarchy is visible while choosing. */
export function UnitSelect({ value, onChange, emptyLabel, className, ...rest }: UnitSelectProps) {
  const { units } = useUnits()
  return (
    <select className={['select', className].filter(Boolean).join(' ')} value={value} onChange={(event) => onChange(event.target.value)} {...rest}>
      {emptyLabel !== undefined && <option value="">{emptyLabel}</option>}
      {units.map((unit) => (
        <option key={unit.id} value={unit.id}>{INDENT.repeat(unit.depth)}{unit.name}</option>
      ))}
    </select>
  )
}
