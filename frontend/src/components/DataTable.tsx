import type { KeyboardEvent, MouseEvent, ReactNode } from 'react'
import { Checkbox } from './Checkbox'
import { Skeleton } from './Skeleton'

export interface Column<T> {
  key: string
  header: string
  render: (row: T) => ReactNode
  /** Keep the cell on one line. */
  nowrap?: boolean
  /** Right-aligned tabular numbers. */
  numeric?: boolean
  align?: 'left' | 'right' | 'center'
  width?: number | string
  /** Hide this column below a width: `md` 768, `lg` 1024, `xl` 1280 px. Hidden columns also vanish from phone cards, so keep key data visible. */
  hideBelow?: 'md' | 'lg' | 'xl'
  /** Phone cards print this cell without its label (the card title). */
  primary?: boolean
  /** Header is read by screen readers only (an actions column). */
  srHeader?: boolean
}

export interface RowSelection<K extends string | number> {
  selected: ReadonlySet<K>
  onChange: (next: Set<K>) => void
}

interface DataTableProps<T, K extends string | number = string | number> {
  columns: Column<T>[]
  rows: T[]
  getKey: (row: T) => K
  /** Names the table for assistive technology. */
  caption: string
  /** The row that is open in a drawer / panel. */
  selectedKey?: K | null
  /** When set, rows are focusable and activate with click, Enter or Space. */
  onSelect?: (row: T) => void
  /** Adds a checkbox column for bulk actions. */
  selection?: RowSelection<K>
  /** Accessible name of a row's checkbox. */
  rowLabel?: (row: T) => string
  /** Shows skeleton rows while no data has arrived yet. Keep passing the old rows during a reload to avoid flicker. */
  loading?: boolean
  skeletonRows?: number
  /** Shown instead of the body when there are no rows (an `EmptyState`). */
  empty?: ReactNode
  /** Footer row inside the card: usually `<Pagination className="table-foot" …/>`. */
  footer?: ReactNode
  density?: 'comfortable' | 'compact'
  rowClassName?: (row: T) => string | undefined
}

function cellClass<T>(column: Column<T>): string | undefined {
  const align = column.align ?? (column.numeric ? 'right' : undefined)
  return (
    [column.nowrap && 'nowrap', column.numeric && 'tnum', align === 'right' && 'is-right', align === 'center' && 'is-center', column.hideBelow && `hide-${column.hideBelow}`]
      .filter(Boolean)
      .join(' ') || undefined
  )
}

/**
 * Data table in a card: sticky header (sticks to the top of the scrolling page), 56 px rows with a strong first line and a
 * muted second line (`.cell-main` / `.cell-sub`), hover / selected states, optional checkbox column, skeleton rows while
 * loading, an empty slot, and stacked cards on phones. Wide pages should hide secondary columns with `hideBelow`.
 */
export function DataTable<T, K extends string | number = string | number>({
  columns,
  rows,
  getKey,
  caption,
  selectedKey,
  onSelect,
  selection,
  rowLabel,
  loading = false,
  skeletonRows = 6,
  empty,
  footer,
  density = 'comfortable',
  rowClassName,
}: DataTableProps<T, K>) {
  const showSkeleton = loading && rows.length === 0
  const showEmpty = !loading && rows.length === 0 && empty

  const onRowKey = (event: KeyboardEvent<HTMLTableRowElement>, row: T) => {
    if (event.target !== event.currentTarget) return
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      onSelect?.(row)
    }
  }
  const stop = (event: MouseEvent) => event.stopPropagation()

  const allKeys = rows.map(getKey)
  const pickedCount = selection ? allKeys.filter((key) => selection.selected.has(key)).length : 0
  const toggleAll = (checked: boolean) => {
    if (!selection) return
    const next = new Set(selection.selected)
    for (const key of allKeys) {
      if (checked) next.add(key)
      else next.delete(key)
    }
    selection.onChange(next)
  }
  const toggleOne = (key: K, checked: boolean) => {
    if (!selection) return
    const next = new Set(selection.selected)
    if (checked) next.add(key)
    else next.delete(key)
    selection.onChange(next)
  }

  return (
    <div className="table-card" aria-busy={loading || undefined}>
      {showEmpty ? (
        empty
      ) : (
        <table className={['table', density === 'compact' && 'table--compact'].filter(Boolean).join(' ')}>
          <caption className="sr-only">{caption}</caption>
          <thead>
            <tr>
              {selection && (
                <th scope="col" className="col-select">
                  <Checkbox
                    aria-label="Chọn tất cả các dòng đang hiển thị"
                    checked={rows.length > 0 && pickedCount === rows.length}
                    indeterminate={pickedCount > 0 && pickedCount < rows.length}
                    onChange={toggleAll}
                    disabled={rows.length === 0}
                  />
                </th>
              )}
              {columns.map((column) => (
                <th key={column.key} scope="col" className={cellClass(column)} style={column.width !== undefined ? { width: column.width } : undefined}>
                  {column.srHeader ? <span className="sr-only">{column.header}</span> : column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {showSkeleton
              ? Array.from({ length: skeletonRows }, (_, index) => (
                  <tr key={index} aria-hidden="true">
                    {selection && <td className="col-select"><Skeleton width={18} height={18} /></td>}
                    {columns.map((column, columnIndex) => (
                      <td key={column.key} className={cellClass(column)} data-label={column.primary ? undefined : column.header}>
                        <Skeleton width={`${columnIndex === 0 ? 70 : 45 + ((index * 17 + columnIndex * 23) % 45)}%`} height={14} />
                      </td>
                    ))}
                  </tr>
                ))
              : rows.map((row) => {
                  const key = getKey(row)
                  const selected = key === selectedKey
                  const picked = selection?.selected.has(key) ?? false
                  const classes = [selected && 'is-selected', picked && 'is-picked', onSelect && 'is-clickable', rowClassName?.(row)].filter(Boolean).join(' ') || undefined
                  return (
                    <tr
                      key={key}
                      className={classes}
                      aria-current={selected || undefined}
                      tabIndex={onSelect ? 0 : undefined}
                      onClick={onSelect ? () => onSelect(row) : undefined}
                      onKeyDown={onSelect ? (event) => onRowKey(event, row) : undefined}
                    >
                      {selection && (
                        <td className="col-select" onClick={stop}>
                          <Checkbox aria-label={rowLabel ? `Chọn ${rowLabel(row)}` : 'Chọn dòng'} checked={picked} onChange={(checked) => toggleOne(key, checked)} />
                        </td>
                      )}
                      {columns.map((column) => (
                        <td key={column.key} className={cellClass(column)} data-label={column.primary || column.srHeader ? undefined : column.header}>
                          {column.render(row)}
                        </td>
                      ))}
                    </tr>
                  )
                })}
          </tbody>
        </table>
      )}
      {footer}
    </div>
  )
}
