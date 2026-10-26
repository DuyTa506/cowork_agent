import { useState, type KeyboardEvent, type PointerEvent } from 'react'
import { compact, full, niceScale } from './scale'
import { useWidth } from './useWidth'

export interface TimePoint {
  /** x-axis text (short). */
  tick: string
  /** First line of the tooltip. */
  title: string
  value: number
}

interface TimeChartProps {
  points: TimePoint[]
  kind: 'line' | 'columns'
  /** What the values count: "câu hỏi", "văn bản" (tooltip and speech). */
  unit: string
  label: string
  height?: number
}

const PAD = { top: 22, right: 16, bottom: 26, left: 40 }
const COLUMN_MAX = 24 // px: a column never fills its slot

/**
 * One series over time: a 2 px line with a 10 % wash and a marked last point, or columns (≤ 24 px, 4 px rounded tops). Hairline grid,
 * round-number ticks, the last value labelled and every other value in the tooltip, which follows the pointer or the arrow keys.
 */
export function TimeChart({ points, kind, unit, label, height = 220 }: TimeChartProps) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const [active, setActive] = useState<number | null>(null)
  const innerW = width - PAD.left - PAD.right
  const innerH = height - PAD.top - PAD.bottom
  const max = Math.max(0, ...points.map((p) => p.value))
  const { top, ticks } = niceScale(max)
  const n = points.length
  const slot = n > 0 ? innerW / n : innerW
  const xAt = (i: number) => PAD.left + (kind === 'columns' ? slot * (i + 0.5) : n <= 1 ? innerW / 2 : (i / (n - 1)) * innerW)
  const yAt = (v: number) => PAD.top + innerH - (v / top) * innerH
  const every = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(innerW / 54))))
  const last = n - 1
  const peak = points.reduce((best, p, i) => (p.value > (points[best]?.value ?? -1) ? i : best), 0)

  const indexAt = (event: PointerEvent<SVGSVGElement>): number => {
    const box = event.currentTarget.getBoundingClientRect()
    const x = event.clientX - box.left - PAD.left
    return Math.min(n - 1, Math.max(0, kind === 'columns' ? Math.floor(x / slot) : Math.round((x / innerW) * (n - 1))))
  }
  const onKey = (event: KeyboardEvent<SVGSVGElement>) => {
    const step = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0
    if (step === 0) return
    event.preventDefault()
    setActive((current) => Math.min(n - 1, Math.max(0, (current ?? (step > 0 ? -1 : n)) + step)))
  }

  const shown = active !== null ? points[active] : undefined
  const line = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${xAt(i).toFixed(1)},${yAt(p.value).toFixed(1)}`).join(' ')
  const area = n > 1 ? `${line} L${xAt(last).toFixed(1)},${yAt(0)} L${xAt(0).toFixed(1)},${yAt(0)} Z` : ''
  const thick = Math.min(COLUMN_MAX, Math.max(4, slot - 6))

  return (
    <div className="timechart" ref={ref}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="group" tabIndex={0}
           aria-label={`${label}. Dùng phím mũi tên trái phải để xem từng mốc.`}
           onPointerMove={(e) => setActive(indexAt(e))} onPointerLeave={() => setActive(null)} onKeyDown={onKey} onBlur={() => setActive(null)}>
        {ticks.map((tick) => (
          <g key={tick}>
            <line className={tick === 0 ? 'axis' : 'grid'} x1={PAD.left} x2={width - PAD.right} y1={yAt(tick)} y2={yAt(tick)} />
            <text className="tick" x={PAD.left - 8} y={yAt(tick)} textAnchor="end" dominantBaseline="central">{compact(tick)}</text>
          </g>
        ))}
        {points.map((p, i) => (i % every === 0 || i === last) && (i === last || last - i >= every * 0.7) ? (
          <text key={p.tick + i} className="tick" x={xAt(i)} y={height - 8} textAnchor={i === last && kind === 'line' ? 'end' : 'middle'}>{p.tick}</text>
        ) : null)}

        {kind === 'line' ? (
          <>
            {area && <path className="area" d={area} />}
            <path className="line" d={line} fill="none" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
          </>
        ) : (
          points.map((p, i) => {
            const h = (p.value / top) * innerH
            const r = Math.min(4, h)
            const x = xAt(i) - thick / 2
            const y = yAt(p.value)
            return (
              <path key={p.tick + i} className={active === i ? 'column column--on' : 'column'}
                    d={h <= 0 ? '' : `M${x},${y + h} V${y + r} Q${x},${y} ${x + r},${y} H${x + thick - r} Q${x + thick},${y} ${x + thick},${y + r} V${y + h} Z`} />
            )
          })
        )}

        {shown && active !== null && kind === 'line' && <line className="crosshair" x1={xAt(active)} x2={xAt(active)} y1={PAD.top} y2={PAD.top + innerH} />}
        {kind === 'line' && n > 0 && (
          <circle className="enddot" cx={xAt(shown && active !== null ? active : last)} cy={yAt((shown ?? points[last])?.value ?? 0)} r={5} strokeWidth={2} />
        )}
        {n > 0 && max > 0 && (kind === 'line' ? (
          <text className="valuelabel" x={xAt(last) - 12} y={yAt(points[last]?.value ?? 0)} textAnchor="end" dominantBaseline="central">{full(points[last]?.value ?? 0)}</text>
        ) : (
          [...new Set([peak, last])].map((i) => (
            <text key={i} className="valuelabel" x={xAt(i)} y={yAt(points[i]?.value ?? 0) - 6} textAnchor="middle">{full(points[i]?.value ?? 0)}</text>
          ))
        ))}
      </svg>
      {shown && active !== null && (
        <div className="tooltip" role="status" style={{ left: Math.min(width - 150, Math.max(0, xAt(active) - 60)), top: 6 }}>
          <span className="tooltip__title">{shown.title}</span>
          <span className="tooltip__value tnum">{full(shown.value)} {unit}</span>
        </div>
      )}
    </div>
  )
}
