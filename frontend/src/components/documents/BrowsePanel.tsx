import { useMemo, useState } from 'react'
import type { Facets, FacetValue, Unit } from '../../api'
import { isYearTag, yearOf, yearRange, type DocumentFilters } from '../../lib/documentFilters'
import { formatNumber } from '../../lib/format'
import { IconButton } from '../IconButton'
import { Icon } from '../Icon'

interface BrowsePanelProps {
  /** null while loading. */
  facets: Facets | null
  units: Unit[]
  filters: DocumentFilters
  onChange: (patch: Partial<DocumentFilters>) => void
  onHide: () => void
}

const TYPES_SHOWN = 8
const TAGS_SHOWN = 12

/**
 * The left panel of the Kho: the organisation chart folded to its top unit (a click on a name filters by that unit and everything
 * under it, the arrow opens the branch) and groups of chips (type, year, tag) with the number of documents behind each.
 */
export function BrowsePanel({ facets, units, filters, onChange, onHide }: BrowsePanelProps) {
  return (
    <aside className="browse" aria-label="Duyệt kho văn bản">
      <header className="browse__head">
        <h2 className="browse__title">Duyệt kho</h2>
        <IconButton icon="panelLeftClose" label="Ẩn bảng duyệt kho" size={18} onClick={onHide} />
      </header>
      <div className="browse__scroll">
        <UnitBrowse facets={facets} units={units} selected={filters.unitId} onSelect={(unitId) => onChange({ unitId })} />
        <ChipGroup
          title="Loại văn bản"
          values={facets?.types ?? null}
          shown={TYPES_SHOWN}
          selected={filters.types}
          onToggle={(type) => onChange({ types: toggle(filters.types, type) })}
        />
        <ChipGroup
          title="Năm ban hành"
          values={facets ? [...facets.years].sort((a, b) => b.value.localeCompare(a.value)) : null}
          shown={8}
          selected={yearOf(filters) ? [yearOf(filters)] : []}
          onToggle={(year) => onChange(yearOf(filters) === year ? { dateFrom: '', dateTo: '' } : yearRange(year))}
        />
        <ChipGroup
          title="Thẻ"
          values={facets ? facets.tags.filter((tag) => !isYearTag(tag.value)) : null}
          shown={TAGS_SHOWN}
          selected={filters.tags}
          onToggle={(tag) => onChange({ tags: toggle(filters.tags, tag) })}
          hint="Chọn nhiều thẻ để thu hẹp: văn bản phải có đủ các thẻ đã chọn."
        />
      </div>
    </aside>
  )
}

function toggle(list: string[], value: string): string[] {
  return list.includes(value) ? list.filter((item) => item !== value) : [...list, value]
}

interface ChipGroupProps {
  title: string
  values: FacetValue[] | null
  shown: number
  selected: readonly string[]
  onToggle: (value: string) => void
  hint?: string
}

function ChipGroup({ title, values, shown, selected, onToggle, hint }: ChipGroupProps) {
  const [all, setAll] = useState(false)
  if (values === null) {
    return (
      <section className="bgroup" aria-busy="true" aria-label={title}>
        <h3 className="bgroup__title section-label">{title}</h3>
        <div className="bgroup__chips">{[64, 88, 72, 56].map((w) => <span key={w} className="skeleton skeleton--chip" style={{ width: w }} />)}</div>
      </section>
    )
  }
  if (values.length === 0) return null
  // A chosen value that fell outside the short list stays visible, so the filter can be undone from here.
  const head = values.slice(0, shown)
  const extra = values.slice(shown)
  const pinned = extra.filter((item) => selected.includes(item.value))
  const visible = all ? values : [...head, ...pinned]
  const hidden = values.length - visible.length
  return (
    <section className="bgroup" aria-label={title}>
      <h3 className="bgroup__title section-label">{title}</h3>
      {hint && <p className="bgroup__hint">{hint}</p>}
      <div className="bgroup__chips">
        {visible.map((item) => {
          const on = selected.includes(item.value)
          return (
            <button key={item.value} type="button" className={on ? 'fchip is-on' : 'fchip'} aria-pressed={on} onClick={() => onToggle(item.value)}>
              <span className="fchip__label">{item.value}</span>
              <span className="fchip__count tnum">{formatNumber(item.count)}</span>
            </button>
          )
        })}
      </div>
      {(hidden > 0 || (all && extra.length > 0)) && (
        <button type="button" className="bgroup__more" aria-expanded={all} onClick={() => setAll(!all)}>
          {all ? 'Thu gọn' : `Xem thêm ${formatNumber(hidden)}`}
        </button>
      )}
    </section>
  )
}

interface UnitBrowseProps {
  facets: Facets | null
  units: Unit[]
  selected: string
  onSelect: (unitId: string) => void
}

/** The organisation chart with the number of documents of each unit and everything under it; units without documents are left out. */
function UnitBrowse({ facets, units, selected, onSelect }: UnitBrowseProps) {
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set())

  const { children, totals, byId } = useMemo(() => {
    const direct = new Map((facets?.units ?? []).map((item) => [item.value, item.count]))
    const kids = new Map<string, Unit[]>()
    for (const unit of units) kids.set(unit.parent, [...(kids.get(unit.parent) ?? []), unit])
    const sums = new Map<string, number>()
    const total = (unit: Unit): number => {
      const sum = (direct.get(unit.id) ?? 0) + (kids.get(unit.id) ?? []).reduce((acc, child) => acc + total(child), 0)
      sums.set(unit.id, sum)
      return sum
    }
    units.filter((unit) => unit.depth === 0).forEach(total)
    return { children: kids, totals: sums, byId: new Map(units.map((unit) => [unit.id, unit])) }
  }, [facets, units])

  // The branch holding the chosen unit stays open, whatever the user folded, so the filter is never hidden.
  const forced = useMemo(() => {
    const ids = new Set<string>()
    for (let unit = byId.get(selected); unit; unit = byId.get(unit.parent)) if (unit.id !== selected) ids.add(unit.id)
    return ids
  }, [byId, selected])
  const isOpen = (id: string) => open.has(id) || forced.has(id)

  const flip = (id: string) => setOpen((current) => {
    const next = new Set(current)
    if (!next.delete(id)) next.add(id)
    return next
  })

  const visible = units.filter((unit) => {
    if ((totals.get(unit.id) ?? 0) === 0 && unit.id !== selected) return false
    for (let parent = byId.get(unit.parent); parent; parent = byId.get(parent.parent)) if (!isOpen(parent.id)) return false
    return true
  })

  return (
    <section className="bgroup" aria-label="Đơn vị">
      <h3 className="bgroup__title section-label">Đơn vị</h3>
      {facets === null ? (
        <div className="bgroup__chips">{[120, 96, 110].map((w) => <span key={w} className="skeleton skeleton--line" style={{ width: w }} />)}</div>
      ) : (
        <ul className="utree" role="tree">
          {visible.map((unit) => {
            const branch = (children.get(unit.id) ?? []).some((child) => (totals.get(child.id) ?? 0) > 0)
            const expanded = isOpen(unit.id)
            const on = unit.id === selected
            const count = totals.get(unit.id) ?? 0
            return (
              <li key={unit.id} role="treeitem" aria-expanded={branch ? expanded : undefined} aria-selected={on} className={on ? 'utree__row is-on' : 'utree__row'} style={{ paddingLeft: 4 + unit.depth * 14 }}>
                {branch ? (
                  <button type="button" className="utree__twist" aria-label={`${expanded ? 'Thu gọn' : 'Mở'} ${unit.name}`} onClick={() => flip(unit.id)}>
                    <Icon name={expanded ? 'chevronDown' : 'chevronRight'} size={16} />
                  </button>
                ) : (
                  <span className="utree__twist utree__twist--leaf" aria-hidden="true" />
                )}
                <button type="button" className="utree__name" title={unit.name} onClick={() => onSelect(on ? '' : unit.id)}>{unit.name}</button>
                <span className="utree__count tnum">{formatNumber(count)}</span>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
