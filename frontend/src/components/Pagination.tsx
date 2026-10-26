import { formatNumber } from '../lib/format'
import { Button } from './Button'

interface PaginationProps {
  offset: number
  limit: number
  total: number
  /** Noun after the count, for example "văn bản". */
  noun: string
  onOffsetChange: (offset: number) => void
  /** Drop the outer padding when it sits in a `.table-foot`. */
  className?: string
}

/** "1–20 trong 1.562 văn bản" with previous / next buttons. */
export function Pagination({ offset, limit, total, noun, onOffsetChange, className }: PaginationProps) {
  if (total === 0) return null
  const pages = Math.max(1, Math.ceil(total / limit))
  const page = Math.floor(offset / limit) + 1
  const last = Math.min(offset + limit, total)
  return (
    <nav className={['pagination', className].filter(Boolean).join(' ')} aria-label="Phân trang">
      <span className="tnum">{formatNumber(offset + 1)}–{formatNumber(last)} trong {formatNumber(total)} {noun}</span>
      <span className="pagination__controls">
        <Button size="sm" icon="chevronLeft" onClick={() => onOffsetChange(Math.max(0, offset - limit))} disabled={page <= 1}>Trước</Button>
        <span className="pagination__page" aria-current="page">Trang {formatNumber(page)} / {formatNumber(pages)}</span>
        <Button size="sm" iconEnd="chevronRight" onClick={() => onOffsetChange(offset + limit)} disabled={page >= pages}>Sau</Button>
      </span>
    </nav>
  )
}
