import { Link } from 'react-router-dom'
import { full } from './scale'

export interface BarItem {
  key: string
  label: string
  value: number
  /** Small grey text after the label (the branch a unit belongs to). */
  note?: string
  /** Makes the label a link (a bar of the document types opens the store filtered to it). */
  href?: string
}

interface BarListProps {
  items: BarItem[]
  /** Names the list for assistive technology. */
  label: string
  /** Unit after the value ("văn bản"), spoken but not drawn. */
  unit?: string
}

/** Horizontal bars, longest first: label, bar from a single baseline (4 px rounded at the data end) and the value at its tip. */
export function BarList({ items, label, unit = '' }: BarListProps) {
  const max = Math.max(1, ...items.map((item) => item.value))
  return (
    <ul className="barlist" aria-label={label}>
      {items.map((item) => (
        <li key={item.key} className="barlist__row">
          <span className="barlist__label" title={item.note ? `${item.label} · ${item.note}` : item.label}>
            {item.href ? <Link to={item.href}>{item.label}</Link> : item.label}
            {item.note && <span className="barlist__note">{item.note}</span>}
          </span>
          <span className="barlist__track" aria-hidden="true">
            <span className="barlist__bar" style={{ width: `${Math.max(item.value > 0 ? 1.5 : 0, (item.value / max) * 100)}%` }} />
          </span>
          <span className="barlist__value tnum">
            {full(item.value)}
            {unit && <span className="sr-only"> {unit}</span>}
          </span>
        </li>
      ))}
    </ul>
  )
}
