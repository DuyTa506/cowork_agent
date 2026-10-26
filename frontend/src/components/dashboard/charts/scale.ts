/** Number formatting and axis helpers shared by the dashboard charts. */

const VI = new Intl.NumberFormat('vi-VN')

/** 1.234 (full, for tables and tooltips). */
export const full = (value: number): string => VI.format(value)

/** 0 / 950 / 1,2 N / 3,4 Tr: compact from 1.000 up, for axis ticks and tips. */
export function compact(value: number): string {
  const abs = Math.abs(value)
  if (abs >= 1_000_000) return `${trim(value / 1_000_000)} Tr`
  if (abs >= 10_000) return `${trim(value / 1000)} N`
  return full(value)
}

const trim = (n: number): string => VI.format(Math.round(n * 10) / 10)

/** Round-number ceiling and ticks (0, step, 2·step…) so that the top tick is not far above the data. */
export function niceScale(max: number, target = 4): { top: number; ticks: number[] } {
  if (max <= 0) return { top: 4, ticks: [0, 2, 4] }
  const raw = max / target
  const pow = 10 ** Math.floor(Math.log10(raw))
  const step = ([1, 2, 2.5, 5, 10].find((m) => m * pow >= raw) ?? 10) * pow
  const top = Math.ceil(max / step) * step
  const ticks: number[] = []
  for (let v = 0; v <= top + 1e-9; v += step) ticks.push(Math.round(v * 100) / 100)
  return { top, ticks }
}

/** "2026-10-26" -> "26/10" */
export function shortDay(iso: string): string {
  const [, month, day] = iso.split('-')
  return `${Number(day)}/${Number(month)}`
}

/** "2026-10-26" -> "26/10/2026" */
export function longDay(iso: string): string {
  const [year, month, day] = iso.split('-')
  return `${day}/${month}/${year}`
}

/** "2026-10" -> "T10" ("T1/26" for a January, so the year shows where it changes). */
export function shortMonth(key: string): string {
  const [year, month] = key.split('-')
  return Number(month) === 1 ? `T1/${year?.slice(2)}` : `T${Number(month)}`
}

/** "2026-10" -> "tháng 10/2026" */
export function longMonth(key: string): string {
  const [year, month] = key.split('-')
  return `tháng ${Number(month)}/${year}`
}
