import type { DocumentState } from '../../api'
import { STATE_TABS, tabBreakdown, tabCount, type StateTabKey } from '../../lib/documents'
import { formatNumber } from '../../lib/format'
import { Icon } from '../Icon'

interface StatStripProps {
  /** Per-state counts from the API; null while the first page is loading. */
  counts: Partial<Record<DocumentState, number>> | null
  value: StateTabKey
  onChange: (key: StateTabKey) => void
}

/** Four clickable cards (Tất cả, Sẵn sàng, Đang xử lý, Cần xử lý): a big count, a label and a coloured bar; they filter the list by state. */
export function StatStrip({ counts, value, onChange }: StatStripProps) {
  return (
    <div className="stats" role="group" aria-label="Lọc theo trạng thái">
      {STATE_TABS.map((tab) => {
        const selected = tab.key === value
        const count = counts ? tabCount(tab, counts) : null
        const detail = counts ? tabBreakdown(tab, counts) : ''
        return (
          <button
            key={tab.key}
            type="button"
            className={`stat stat--${tab.tone}${selected ? ' is-on' : ''}`}
            aria-pressed={selected}
            onClick={() => onChange(tab.key)}
          >
            <span className="stat__label">
              <Icon name={tab.icon} size={18} className={tab.key === 'processing' && count ? 'stat__spin' : undefined} />
              {tab.label}
            </span>
            <span className="stat__value tnum">{count === null ? <span className="skeleton stat__skeleton" aria-hidden="true" /> : formatNumber(count)}</span>
            <span className="stat__note">{count === null ? ' ' : detail || (tab.key === 'all' ? 'văn bản trong kho' : 'văn bản')}</span>
          </button>
        )
      })}
    </div>
  )
}
