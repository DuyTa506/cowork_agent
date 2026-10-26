import { useState } from 'react'
import { full } from './scale'

export interface DonutSlice {
  key: string
  label: string
  value: number
  /** CSS colour (a token), so the same slice keeps its colour in both themes. */
  color: string
}

interface DonutProps {
  slices: DonutSlice[]
  /** What the middle number counts ("văn bản"). */
  centerLabel: string
  label: string
}

const SIZE = 168
const STROKE = 24
const RADIUS = (SIZE - STROKE) / 2
const CIRCUMFERENCE = 2 * Math.PI * RADIUS
const GAP = 2 // px of surface between slices

const share = (value: number, total: number): string => {
  if (!total) return ''
  const tenths = Math.round((value / total) * 1000) / 10
  return tenths < 0.1 ? '<0,1%' : `${tenths.toLocaleString('vi-VN')}%`
}

/** Ring with the total in the middle and a legend that carries every value and share, so colour is never the only channel. */
export function Donut({ slices, centerLabel, label }: DonutProps) {
  const [active, setActive] = useState<string | null>(null)
  const visible = slices.filter((slice) => slice.value > 0)
  const total = visible.reduce((sum, slice) => sum + slice.value, 0)
  const shown = visible.find((slice) => slice.key === active)
  let offset = 0
  const arcs = visible.map((slice) => {
    const length = (slice.value / total) * CIRCUMFERENCE
    const arc = { slice, length: Math.max(0, length - (visible.length > 1 ? GAP : 0)), offset }
    offset += length
    return arc
  })
  return (
    <div className="donut">
      <svg className="donut__ring" width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} role="img"
           aria-label={`${label}: ${visible.map((s) => `${s.label} ${full(s.value)}`).join(', ')}`}>
        <circle cx={SIZE / 2} cy={SIZE / 2} r={RADIUS} fill="none" className="donut__track" strokeWidth={STROKE} />
        <g transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}>
          {arcs.map(({ slice, length, offset: start }) => (
            <circle key={slice.key} cx={SIZE / 2} cy={SIZE / 2} r={RADIUS} fill="none" stroke={slice.color}
                    strokeWidth={active === slice.key ? STROKE + 4 : STROKE} strokeDasharray={`${length} ${CIRCUMFERENCE - length}`}
                    strokeDashoffset={-start} onPointerEnter={() => setActive(slice.key)} onPointerLeave={() => setActive(null)} />
          ))}
        </g>
        <text className="donut__num" x="50%" y="48%" textAnchor="middle" dominantBaseline="central">{full(shown ? shown.value : total)}</text>
        <text className="donut__cap" x="50%" y="64%" textAnchor="middle" dominantBaseline="central">{shown ? shown.label : centerLabel}</text>
      </svg>
      <ul className="legend" aria-label={`Chú giải: ${label}`}>
        {visible.map((slice) => (
          <li key={slice.key} className={active === slice.key ? 'legend__item legend__item--on' : 'legend__item'}
              onPointerEnter={() => setActive(slice.key)} onPointerLeave={() => setActive(null)}>
            <span className="legend__swatch" style={{ background: slice.color }} aria-hidden="true" />
            <span className="legend__label">{slice.label}</span>
            <span className="legend__value tnum">{full(slice.value)}</span>
            <span className="legend__share tnum">{share(slice.value, total)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
