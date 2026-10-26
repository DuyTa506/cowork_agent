interface SparklineProps {
  values: number[]
  width?: number
  height?: number
  /** Spoken summary, for example "6 câu hỏi trong 30 ngày". */
  label: string
}

/** A 2 px line without axes for a table cell; the last point is marked. An all-zero series is a flat hairline. */
export function Sparkline({ values, width = 96, height = 24, label }: SparklineProps) {
  const max = Math.max(...values, 0)
  const pad = 4
  const x = (i: number) => pad + (values.length <= 1 ? 0 : (i / (values.length - 1)) * (width - 2 * pad))
  const y = (v: number) => (max === 0 ? height - pad : height - pad - (v / max) * (height - 2 * pad))
  const points = values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ')
  const lastIndex = values.length - 1
  return (
    <svg className={max === 0 ? 'spark spark--flat' : 'spark'} width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label}>
      {values.length > 1 && <polyline points={points} fill="none" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />}
      {max > 0 && lastIndex >= 0 && <circle className="spark__dot" cx={x(lastIndex)} cy={y(values[lastIndex] ?? 0)} r={3.5} strokeWidth={2} />}
    </svg>
  )
}
