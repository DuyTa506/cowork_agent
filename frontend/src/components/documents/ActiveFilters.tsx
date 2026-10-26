import { yearOf, type DocumentFilters } from '../../lib/documentFilters'
import { LEVEL_LABELS } from '../../lib/labels'
import { formatDate } from '../../lib/format'
import { Button } from '../Button'
import { Icon } from '../Icon'

interface ActiveFiltersProps {
  filters: DocumentFilters
  /** Name of a unit id. */
  unitName: (id: string) => string
  /** A state card other than "Tất cả" is on. */
  stateLabel: string
  onChange: (patch: Partial<DocumentFilters>) => void
  onClearState: () => void
  onClearAll: () => void
}

interface Entry {
  key: string
  label: string
  remove: () => void
}

/** The filters in force as removable chips above the list, with "Xóa lọc" to drop them all. */
export function ActiveFilters({ filters, unitName, stateLabel, onChange, onClearState, onClearAll }: ActiveFiltersProps) {
  const entries: Entry[] = []
  if (stateLabel) entries.push({ key: 'state', label: `Trạng thái: ${stateLabel}`, remove: onClearState })
  if (filters.q) entries.push({ key: 'q', label: `Từ khóa: ${filters.q}`, remove: () => onChange({ q: '' }) })
  if (filters.unitId) entries.push({ key: 'unit', label: `Đơn vị: ${unitName(filters.unitId)}`, remove: () => onChange({ unitId: '' }) })
  filters.types.forEach((type) => entries.push({ key: `type:${type}`, label: type, remove: () => onChange({ types: filters.types.filter((t) => t !== type) }) }))
  const year = yearOf(filters)
  if (year) entries.push({ key: 'year', label: `Năm ${year}`, remove: () => onChange({ dateFrom: '', dateTo: '' }) })
  else if (filters.dateFrom || filters.dateTo) {
    const label = `Ban hành ${filters.dateFrom ? `từ ${formatDate(filters.dateFrom)}` : ''} ${filters.dateTo ? `đến ${formatDate(filters.dateTo)}` : ''}`.replace(/\s+/g, ' ').trim()
    entries.push({ key: 'dates', label, remove: () => onChange({ dateFrom: '', dateTo: '' }) })
  }
  if (filters.level) entries.push({ key: 'level', label: `Mức độ: ${LEVEL_LABELS[filters.level]}`, remove: () => onChange({ level: '' }) })
  filters.tags.forEach((tag) => entries.push({ key: `tag:${tag}`, label: tag, remove: () => onChange({ tags: filters.tags.filter((t) => t !== tag) }) }))
  if (entries.length === 0) return null

  return (
    <div className="afilters" role="group" aria-label="Bộ lọc đang áp dụng">
      {entries.map((entry) => (
        <span key={entry.key} className="afilter">
          <span className="afilter__text">{entry.label}</span>
          <button type="button" className="afilter__x" aria-label={`Bỏ lọc ${entry.label}`} onClick={entry.remove}><Icon name="close" size={14} /></button>
        </span>
      ))}
      <Button variant="ghost" size="sm" onClick={onClearAll}>Xóa lọc</Button>
    </div>
  )
}
