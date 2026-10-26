/**
 * Table helpers for the canvas: the heading layout and alignment the Word export uses (backend `app.drafting.tables`), the
 * user's structural edits, and the cell-level comparison behind an assistant's proposed table. Figures are never worked out
 * here: the server computes formula and total cells on every save.
 */
import type { CellAlign, TableColumn, TableRow, TableSpec } from '../../api/chat'

export const GAP = '…'
const FIGURES = /^[\d.,%/()+\-–\s…]*$/
const ORDINAL_LABELS = new Set(['tt', 'stt', 'số tt', 'số thứ tự'])

/** Where a column sits: its index among the top-level columns and, for a sub-column, among its group's children. */
export type ColumnAt = [number, number | null]

export const leaves = (spec: Pick<TableSpec, 'columns'>): TableColumn[] => spec.columns.flatMap((c) => (c.children?.length ? c.children : [c]))

/** A cell still waiting for its figure. */
export const hasGap = (text: string): boolean => text.includes(GAP) || text.includes('...')

export const countGaps = (spec: TableSpec): number => spec.rows.reduce((n, row) => n + row.cells.filter(hasGap).length, 0)

export interface HeadCell {
  label: string
  colSpan: number
  rowSpan: number
  at: ColumnAt
  /** Set when the heading is a leaf column (it has cells). */
  leaf?: TableColumn
}

/** The heading rows: one, or two when a column has sub-columns (a column without them then spans both rows). */
export function header(spec: Pick<TableSpec, 'columns'>): HeadCell[][] {
  const two = spec.columns.some((c) => c.children?.length)
  const top: HeadCell[] = []
  const bottom: HeadCell[] = []
  spec.columns.forEach((column, i) => {
    const children = column.children ?? []
    if (children.length) {
      top.push({ label: column.label, colSpan: children.length, rowSpan: 1, at: [i, null] })
      children.forEach((child, j) => bottom.push({ label: child.label, colSpan: 1, rowSpan: 1, at: [i, j], leaf: child }))
    } else {
      top.push({ label: column.label, colSpan: 1, rowSpan: two ? 2 : 1, at: [i, null], leaf: column })
    }
  })
  return two ? [top, bottom] : [top]
}

/** Alignment per leaf column: as written, else centred for "TT", figures and short values ("Chiếc"), left for text. */
export function aligns(spec: TableSpec): CellAlign[] {
  return leaves(spec).map((leaf, index) => {
    if (leaf.align) return leaf.align
    const values = spec.rows.filter((r) => r.type === 'row' || r.type === 'total').map((r) => r.cells[index] ?? '').filter(Boolean)
    const short = values.length > 0 && Math.max(...values.map((v) => v.length)) <= 8
    const figures = values.length > 0 && values.every((v) => FIGURES.test(v))
    return ORDINAL_LABELS.has(leaf.label.toLowerCase()) || figures || short ? 'center' : 'left'
  })
}

/** Whether the server works the cell out (a formula column, or a column a total/group row adds up): it cannot be typed. */
export function computed(row: TableRow, leaf: TableColumn): boolean {
  if (row.type === 'row') return Boolean(leaf.formula)
  if ((row.type === 'group' || row.type === 'total') && row.sum?.length) return (leaf.id !== undefined && row.sum.includes(leaf.id)) || Boolean(leaf.formula)
  return false
}

/** How a computed cell is obtained, for its tooltip. */
export function computedHint(row: TableRow, leaf: TableColumn, spec: TableSpec): string {
  const label = (id: string) => leaves(spec).find((c) => c.id === id)?.label ?? id
  const formula = (text: string) => text.replace(/\bc\d+\b/g, (id) => `[${label(id)}]`)
  if (row.type === 'row' || !(leaf.id && row.sum?.includes(leaf.id))) return `Tự tính: ${formula(leaf.formula ?? '')}`
  return row.type === 'group' ? 'Tự cộng các dòng của nhóm' : row.scope === 'group' ? 'Tự cộng các dòng trong nhóm' : 'Tự cộng cả bảng'
}

const leafAt = (spec: TableSpec, index: number): ColumnAt => {
  let seen = 0
  for (let i = 0; i < spec.columns.length; i += 1) {
    const children = spec.columns[i].children ?? []
    if (!children.length) {
      if (seen === index) return [i, null]
      seen += 1
      continue
    }
    if (index < seen + children.length) return [i, index - seen]
    seen += children.length
  }
  throw new RangeError(`no leaf column ${index}`)
}

const eachCellRow = (spec: TableSpec, change: (cells: string[]) => void) => {
  for (const row of spec.rows) if (row.type !== 'section') change(row.cells)
}

export function setCell(spec: TableSpec, row: number, col: number, text: string): TableSpec {
  const next = structuredClone(spec)
  next.rows[row].cells[next.rows[row].type === 'section' ? 0 : col] = text
  return next
}

export function setLabel(spec: TableSpec, [top, child]: ColumnAt, label: string): TableSpec {
  const next = structuredClone(spec)
  const column = child === null ? next.columns[top] : next.columns[top].children![child]
  column.label = label
  return next
}

/** A blank ordinary row after row `after` (null: at the end). */
export function insertRow(spec: TableSpec, after: number | null): TableSpec {
  const next = structuredClone(spec)
  const at = after === null ? next.rows.length : after + 1
  next.rows.splice(at, 0, { type: 'row', cells: leaves(next).map(() => '') })
  return next
}

export function deleteRow(spec: TableSpec, index: number): TableSpec {
  const next = structuredClone(spec)
  next.rows.splice(index, 1)
  return next
}

/** A blank column right of leaf column `after`, in the same group (null: at the end). */
export function insertColumn(spec: TableSpec, after: number | null, label = 'Cột mới'): TableSpec {
  const next = structuredClone(spec)
  const width = leaves(next).length
  if (after === null || after >= width) {
    next.columns.push({ label })
    eachCellRow(next, (cells) => cells.push(''))
    return next
  }
  const [top, child] = leafAt(next, after)
  if (child === null) next.columns.splice(top + 1, 0, { label })
  else next.columns[top].children!.splice(child + 1, 0, { label })
  eachCellRow(next, (cells) => cells.splice(after + 1, 0, ''))
  return next
}

/** Removes leaf column `index`, or says why it cannot go (the last column, or a formula reads it). */
export function deleteColumn(spec: TableSpec, index: number): TableSpec | string {
  const all = leaves(spec)
  const leaf = all[index]
  if (all.length <= 1) return 'Bảng phải còn ít nhất một cột.'
  const reader = leaf.id ? all.find((c) => c !== leaf && c.formula && new RegExp(`\\b${leaf.id}\\b`).test(c.formula)) : undefined
  if (reader) return `Cột “${leaf.label}” đang được dùng trong công thức của cột “${reader.label}”: sửa công thức đó trước.`
  const next = structuredClone(spec)
  const [top, child] = leafAt(next, index)
  if (child === null) next.columns.splice(top, 1)
  else {
    next.columns[top].children!.splice(child, 1)
    if (!next.columns[top].children!.length) next.columns.splice(top, 1)
  }
  eachCellRow(next, (cells) => cells.splice(index, 1))
  for (const row of next.rows) if (row.sum && leaf.id) row.sum = row.sum.filter((id) => id !== leaf.id)
  return next
}

// ----- comparison of a table with the assistant's proposal -----

export type Change = 'same' | 'added' | 'removed'

export interface Paired<T> {
  old: T | null
  new: T | null
  oldIndex: number | null
  newIndex: number | null
  state: Change
}

/** Both lists in one order: the new order, with each removed item placed where it stood in the old one. Items pair by id. */
export function pair<T extends { id?: string }>(before: T[], after: T[]): Paired<T>[] {
  const kept = new Set(after.map((item) => item.id).filter(Boolean))
  const oldAt = new Map(before.map((item, i) => [item.id, i] as const).filter(([id]) => id))
  const out: Paired<T>[] = []
  let cursor = 0
  const flushRemoved = (upTo: number) => {
    for (; cursor < upTo; cursor += 1) {
      const item = before[cursor]
      if (!item.id || !kept.has(item.id)) out.push({ old: item, new: null, oldIndex: cursor, newIndex: null, state: 'removed' })
    }
  }
  after.forEach((item, newIndex) => {
    const oldIndex = item.id !== undefined ? oldAt.get(item.id) : undefined
    if (oldIndex === undefined) {
      out.push({ old: null, new: item, oldIndex: null, newIndex, state: 'added' })
      return
    }
    flushRemoved(oldIndex)
    cursor = Math.max(cursor, oldIndex + 1)
    out.push({ old: before[oldIndex], new: item, oldIndex, newIndex, state: 'same' })
  })
  flushRemoved(before.length)
  return out
}

export interface TableDiff {
  columns: Paired<TableColumn>[]
  rows: Paired<TableRow>[]
  /** Columns were added, removed or regrouped: the heading is drawn flat. */
  reshaped: boolean
  changedCells: number
  renamed: number
}

const groupOf = (spec: TableSpec): Map<string | undefined, string> =>
  new Map(spec.columns.flatMap((c, i) => (c.children?.length ? c.children : [c]).map((leaf) => [leaf.id, c.children?.length ? `g${c.id ?? i}` : ''] as const)))

export function cellOf(row: TableRow, col: number | null): string {
  if (row.type === 'section') return row.cells[0] ?? ''
  return col === null ? '' : (row.cells[col] ?? '')
}

export function diffTables(before: TableSpec, after: TableSpec): TableDiff {
  const columns = pair(leaves(before), leaves(after))
  const rows = pair(before.rows, after.rows)
  const oldGroups = groupOf(before)
  const newGroups = groupOf(after)
  const reshaped =
    columns.some((c) => c.state !== 'same') ||
    columns.some((c) => oldGroups.get(c.old?.id) !== newGroups.get(c.new?.id)) ||
    before.columns.length !== after.columns.length
  let changedCells = 0
  for (const row of rows) {
    if (row.state !== 'same') continue
    if (row.old!.type === 'section' || row.new!.type === 'section') {
      if (cellOf(row.old!, 0) !== cellOf(row.new!, 0)) changedCells += 1
      continue
    }
    for (const col of columns) if (col.state === 'same' && cellOf(row.old!, col.oldIndex) !== cellOf(row.new!, col.newIndex)) changedCells += 1
  }
  const renamed = columns.filter((c) => c.state === 'same' && c.old!.label !== c.new!.label).length
  return { columns, rows, reshaped, changedCells, renamed }
}

/** "3 ô đổi, thêm 1 dòng, xóa 1 cột": what a proposed table changes. */
export function describeDiff(diff: TableDiff): string {
  const count = (items: Paired<unknown>[], state: Change) => items.filter((item) => item.state === state).length
  const parts = [
    diff.changedCells && `${diff.changedCells} ô đổi`,
    count(diff.rows, 'added') && `thêm ${count(diff.rows, 'added')} dòng`,
    count(diff.rows, 'removed') && `xóa ${count(diff.rows, 'removed')} dòng`,
    count(diff.columns, 'added') && `thêm ${count(diff.columns, 'added')} cột`,
    count(diff.columns, 'removed') && `xóa ${count(diff.columns, 'removed')} cột`,
    diff.renamed && `đổi tên ${diff.renamed} cột`,
  ].filter(Boolean)
  return parts.join(', ')
}
