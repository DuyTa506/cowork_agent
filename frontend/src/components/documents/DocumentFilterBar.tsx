import { useEffect, useState } from 'react'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import type { DocumentFilters } from '../../lib/documentFilters'
import { LEVEL_LABELS } from '../../lib/labels'
import { DateInput } from '../DateInput'
import { Icon } from '../Icon'
import { Select } from '../Select'

interface DocumentFilterBarProps {
  filters: DocumentFilters
  onChange: (patch: Partial<DocumentFilters>) => void
  /** Shown while the browse panel is hidden: brings it back. */
  onShowPanel?: () => void
  /** Number of filters the browse panel holds (unit, types, tags, year), shown on its button. */
  panelFilters: number
}

const LEVEL_OPTIONS = [
  { value: '', label: 'Mức độ' },
  { value: 'thuong', label: LEVEL_LABELS.thuong },
  { value: 'mat', label: LEVEL_LABELS.mat },
]

/** Search box (debounced), level select and a date range. Unit, type, year and tags are chosen in the browse panel. */
export function DocumentFilterBar({ filters, onChange, onShowPanel, panelFilters }: DocumentFilterBarProps) {
  const [draft, setDraft] = useState(filters.q)
  const debounced = useDebouncedValue(draft, 300)

  useEffect(() => {
    if (debounced !== filters.q) onChange({ q: debounced })
  }, [debounced, filters.q, onChange])
  // The address, "Xóa lọc" or the back button can change the keyword from outside.
  useEffect(() => setDraft(filters.q), [filters.q])

  const active = (value: string) => (value ? 'is-active' : undefined)

  return (
    <form className="fbar" role="search" aria-label="Lọc văn bản" onSubmit={(event) => event.preventDefault()}>
      {onShowPanel && (
        <button type="button" className={panelFilters > 0 ? 'fpanel is-active' : 'fpanel'} onClick={onShowPanel}>
          <Icon name="filter" size={18} />
          Duyệt kho
          {panelFilters > 0 && <span className="fpanel__n tnum">{panelFilters}</span>}
        </button>
      )}
      <label className={draft ? 'fsearch is-active' : 'fsearch'}>
        <Icon name="search" size={18} />
        <input
          type="search"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Số ký hiệu, trích yếu, cơ quan, tên tệp"
          aria-label="Tìm văn bản"
        />
        {draft && (
          <button type="button" className="fsearch__clear" aria-label="Xóa từ khóa" onClick={() => { setDraft(''); onChange({ q: '' }) }}>
            <Icon name="close" size={16} />
          </button>
        )}
      </label>
      <Select className={active(filters.level)} aria-label="Mức độ" value={filters.level} options={LEVEL_OPTIONS} onChange={(level) => onChange({ level: level as DocumentFilters['level'] })} />
      <fieldset className={filters.dateFrom || filters.dateTo ? 'fdates is-active' : 'fdates'}>
        <legend className="sr-only">Ngày ban hành</legend>
        <Icon name="calendar" size={18} />
        <DateInput aria-label="Ban hành từ ngày" value={filters.dateFrom} onChange={(dateFrom) => onChange({ dateFrom })} />
        <Icon name="arrowRight" size={14} />
        <DateInput aria-label="Ban hành đến ngày" value={filters.dateTo} onChange={(dateTo) => onChange({ dateTo })} />
      </fieldset>
    </form>
  )
}
