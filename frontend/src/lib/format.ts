const numberFormat = new Intl.NumberFormat('vi-VN')

/** 1562 -> "1.562" */
export function formatNumber(value: number): string {
  return numberFormat.format(value)
}

const pad = (value: number): string => String(value).padStart(2, '0')

/** ISO date `yyyy-mm-dd` -> `dd/mm/yyyy`; an empty or unrecognised value gives `fallback`. */
export function formatDate(iso: string, fallback = '—'): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  return match ? `${match[3]}/${match[2]}/${match[1]}` : fallback
}

/**
 * `dd/mm/yyyy` -> ISO `yyyy-mm-dd`. Returns null when the text is not a real calendar date.
 * Accepts `-` or `.` as separators and one-digit day/month.
 */
export function parseDate(text: string): string | null {
  const match = /^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$/.exec(text.trim())
  if (!match) return null
  const [day, month, year] = [Number(match[1]), Number(match[2]), Number(match[3])]
  const probe = new Date(Date.UTC(year, month - 1, day))
  const real = probe.getUTCFullYear() === year && probe.getUTCMonth() === month - 1 && probe.getUTCDate() === day
  return real ? `${year}-${pad(month)}-${pad(day)}` : null
}

/** The server stores UTC but SQLite hands timestamps back without a zone; treat those as UTC. */
function parseTimestamp(value: string): Date {
  return new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(value) ? value : `${value}Z`)
}

/** Timestamp -> `dd/mm/yyyy HH:mm` in local time. */
export function formatDateTime(value: string | null): string {
  if (!value) return '—'
  const date = parseTimestamp(value)
  if (Number.isNaN(date.getTime())) return '—'
  return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

/** Timestamp -> `HH:mm` in local time. */
export function formatTime(value: string | null): string {
  if (!value) return ''
  const date = parseTimestamp(value)
  return Number.isNaN(date.getTime()) ? '' : `${pad(date.getHours())}:${pad(date.getMinutes())}`
}

/** Bytes -> "1,4 MB". */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${formatNumber(bytes)} B`
  const units = ['KB', 'MB', 'GB']
  let value = bytes / 1024
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 1 }).format(value)} ${units[unit]}`
}

/** "Nguyễn Văn A" -> "NA" (first letters of the first and last word). */
export function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean)
  if (words.length === 0) return '?'
  const first = words[0] ?? ''
  const last = words[words.length - 1] ?? ''
  return (words.length === 1 ? first.slice(0, 2) : first.charAt(0) + last.charAt(0)).toLocaleUpperCase('vi-VN')
}
