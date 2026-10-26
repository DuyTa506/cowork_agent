import { useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import type { TableColumn, TableSpec } from '../../api/chat'
import { Button } from '../Button'
import { Icon } from '../Icon'
import { InlineEditor } from './InlineEditor'
import {
  aligns,
  cellOf,
  computed,
  computedHint,
  countGaps,
  deleteColumn,
  deleteRow,
  diffTables,
  hasGap,
  header,
  insertColumn,
  insertRow,
  leaves,
  setCell,
  setLabel,
  type ColumnAt,
  type Paired,
} from './table'

const MAX_COLUMNS = 16
const MAX_ROWS = 500

type Editing = { kind: 'cell'; row: number; col: number } | { kind: 'head'; at: ColumnAt } | null

const sameAt = (a: ColumnAt, b: ColumnAt) => a[0] === b[0] && a[1] === b[1]
const classes = (...names: (string | false | null | undefined)[]) => names.filter(Boolean).join(' ')

interface TableNotesProps {
  gaps: number
  problems?: string[]
  tooWide?: boolean
  refusal?: string
}

function TableNotes({ gaps, problems = [], tooWide, refusal }: TableNotesProps) {
  if (!gaps && !problems.length && !tooWide && !refusal) return null
  return (
    <ul className="cv-tb__notes cv-ui">
      {refusal && <li className="cv-tb__note cv-tb__note--danger"><Icon name="alertCircle" size={14} />{refusal}</li>}
      {gaps > 0 && <li className="cv-tb__note cv-tb__note--warn"><Icon name="alert" size={14} />Còn {gaps} ô “…” chờ điền số liệu.</li>}
      {problems.map((problem) => <li key={problem} className="cv-tb__note cv-tb__note--danger"><Icon name="sigma" size={14} />{problem}</li>)}
      {tooWide && <li className="cv-tb__note cv-tb__note--warn"><Icon name="landscape" size={14} />Bảng rộng hơn khổ giấy dọc: nên chuyển vào phụ lục để in khổ ngang.</li>}
    </ul>
  )
}

interface TableEditorProps {
  spec: TableSpec
  /** False while the assistant works or a proposal waits: the table is only shown. */
  editable: boolean
  onChange?: (spec: TableSpec) => Promise<void>
  problems?: string[]
  tooWide?: boolean
  /** Block-level buttons shown with the table's own (add a paragraph, delete the table). */
  tools?: ReactNode
}

/**
 * A table on the page, drawn like the Word export: grid lines, a heading of one or two levels, bold group and total rows, a
 * section row across the table. Clicking a cell or heading edits it in place; the toolbar adds or removes the row and column of
 * the chosen cell. Cells the server works out (formulas, sums) cannot be typed, and cells still holding "…" are highlighted.
 * Each change saves the whole table; the page shows it at once and takes the server's copy (with recomputed figures) when the
 * saves are done.
 */
export function TableEditor({ spec: saved, editable, onChange, problems, tooWide, tools }: TableEditorProps) {
  const [optimistic, setOptimistic] = useState<TableSpec | null>(null)
  const [editing, setEditing] = useState<Editing>(null)
  const [chosen, setChosen] = useState<{ row: number; col: number } | null>(null)
  const [refusal, setRefusal] = useState('')
  const queue = useRef<Promise<void>>(Promise.resolve())
  const pending = useRef(0)
  const spec = optimistic ?? saved
  // Edits started in the same event as a commit (blur, then a toolbar click) must build on the committed table.
  const latest = useRef(spec)
  latest.current = spec
  const columns = leaves(spec)
  const align = aligns(spec)
  const spot = chosen && chosen.row < spec.rows.length && chosen.col < columns.length ? chosen : null

  const save = (next: TableSpec) => {
    if (!onChange) return
    latest.current = next
    setOptimistic(next)
    setRefusal('')
    pending.current += 1
    queue.current = queue.current
      .then(() => onChange(next))
      .catch(() => undefined)
      .finally(() => {
        pending.current -= 1
        if (pending.current === 0) setOptimistic(null)
      })
  }

  const cell = (r: number, c: number, span?: number) => {
    const row = spec.rows[r]
    const leaf = columns[c]
    const text = cellOf(row, c)
    const auto = row.type !== 'section' && computed(row, leaf)
    if (editing?.kind === 'cell' && editing.row === r && editing.col === c) {
      return (
        <td key={c} colSpan={span} className="cv-tb__cell cv-tb__cell--editing" style={span ? undefined : { textAlign: align[c] }}>
          <InlineEditor
            value={text}
            label={row.type === 'section' ? 'Dòng tiêu đề nhóm' : `Ô “${leaf.label}”, dòng ${r + 1}`}
            className="cv-tb__editor"
            onCommit={(value) => {
              setEditing(null)
              save(setCell(latest.current, r, c, value.trim()))
            }}
            onCancel={() => setEditing(null)}
          />
        </td>
      )
    }
    const open = () => {
      if (!editable) return
      setChosen({ row: r, col: c })
      if (!auto) setEditing({ kind: 'cell', row: r, col: c })
    }
    const hint = auto ? computedHint(row, leaf, spec) : hasGap(text) ? 'Chưa có số liệu' : undefined
    return (
      <td
        key={c}
        colSpan={span}
        title={hint}
        className={classes('cv-tb__cell', auto && 'cv-tb__cell--auto', hasGap(text) && 'cv-tb__cell--gap', editable && 'cv-tb__cell--editable',
                           spot?.row === r && spot.col === c && 'cv-tb__cell--chosen')}
        style={span ? undefined : { textAlign: align[c] }}
        {...(editable
          ? {
              tabIndex: 0,
              onClick: open,
              onKeyDown: (event: KeyboardEvent) => {
                if (event.key === 'Enter' && event.target === event.currentTarget) {
                  event.preventDefault()
                  open()
                }
              },
            }
          : {})}
      >
        {text}
      </td>
    )
  }

  const heading = (label: string, at: ColumnAt) => {
    if (editing?.kind === 'head' && sameAt(editing.at, at)) {
      return (
        <InlineEditor
          value={label}
          label="Tên cột"
          className="cv-tb__editor"
          onCommit={(value) => {
            setEditing(null)
            if (value.trim()) save(setLabel(latest.current, at, value.trim()))
          }}
          onCancel={() => setEditing(null)}
        />
      )
    }
    return label
  }

  const run = (change: (table: TableSpec) => TableSpec | string) => {
    const next = change(latest.current)
    if (typeof next === 'string') setRefusal(next)
    else save(next)
  }

  return (
    <>
      <div className="cv-tb-wrap">
        <table className="cv-tb">
          <thead>
            {header(spec).map((line, r) => (
              <tr key={r}>
                {line.map((head) => (
                  <th
                    key={head.at.join('.')}
                    scope="col"
                    colSpan={head.colSpan}
                    rowSpan={head.rowSpan}
                    className={classes(editable && 'cv-tb__cell--editable', editing?.kind === 'head' && sameAt(editing.at, head.at) && 'cv-tb__cell--editing')}
                    {...(editable
                      ? {
                          tabIndex: 0,
                          onClick: () => setEditing({ kind: 'head', at: head.at }),
                          onKeyDown: (event: KeyboardEvent) => {
                            if (event.key === 'Enter' && event.target === event.currentTarget) {
                              event.preventDefault()
                              setEditing({ kind: 'head', at: head.at })
                            }
                          },
                        }
                      : {})}
                  >
                    {heading(head.label, head.at)}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {spec.rows.map((row, r) => (
              <tr key={row.id ?? `new-${r}`} className={`cv-tb__row--${row.type}`}>
                {row.type === 'section' ? cell(r, 0, columns.length) : columns.map((_, c) => cell(r, c))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <TableNotes gaps={countGaps(spec)} problems={optimistic ? [] : problems} tooWide={tooWide} refusal={refusal} />
      {editable && (
        <span className="cv-block__tools cv-tb__tools cv-ui">
          <Button size="sm" variant="ghost" icon="rowAdd" disabled={spec.rows.length >= MAX_ROWS} onClick={() => run((t) => insertRow(t, spot?.row ?? null))}>
            Thêm dòng
          </Button>
          <Button size="sm" variant="ghost" icon="trash" disabled={!spot || spec.rows.length <= 1} onClick={() => spot && run((t) => deleteRow(t, spot.row))}>
            Xóa dòng
          </Button>
          <Button size="sm" variant="ghost" icon="columnAdd" disabled={columns.length >= MAX_COLUMNS} onClick={() => run((t) => insertColumn(t, spot?.col ?? null))}>
            Thêm cột
          </Button>
          <Button size="sm" variant="ghost" icon="trash" disabled={!spot || columns.length <= 1} onClick={() => spot && run((t) => deleteColumn(t, spot.col))}>
            Xóa cột
          </Button>
          {tools && <span className="cv-tb__sep" aria-hidden="true" />}
          {tools}
        </span>
      )}
    </>
  )
}

/** A whole table the assistant proposes to add (green) or remove (struck through). */
export function TableMarked({ spec, mark }: { spec: TableSpec; mark: 'ins' | 'del' }) {
  return (
    <div className={`cv-tb-mark cv-tb-mark--${mark}`}>
      <TableEditor spec={spec} editable={false} />
    </div>
  )
}

function Changed({ before, after }: { before: string; after: string }) {
  if (before === after) return <>{after}</>
  return (
    <>
      {before && <del>{before}</del>}
      {before && after && ' '}
      {after && <ins>{after}</ins>}
    </>
  )
}

const groupLabel = (spec: TableSpec, leaf: TableColumn) => spec.columns.find((c) => c.children?.includes(leaf))?.label

/**
 * The assistant's proposed table against the current one, cell by cell: rows and columns pair by id, changed cells show the
 * old figure struck through and the new one, added rows and columns are green, removed ones red. When columns were added,
 * removed or regrouped the heading is drawn on one line ("Số lượng – Đề xuất").
 */
export function TableDiffView({ before, after }: { before: TableSpec; after: TableSpec }) {
  const diff = diffTables(before, after)
  const newAlign = aligns(after)
  const oldAlign = aligns(before)
  const alignOf = (col: Paired<TableColumn>) => (col.newIndex !== null ? newAlign[col.newIndex] : oldAlign[col.oldIndex ?? 0])
  const state = (...states: string[]) => (states.includes('removed') ? 'removed' : states.includes('added') ? 'added' : 'same')
  const stateClass = (s: string) => (s === 'removed' ? 'cv-tb__cell--del' : s === 'added' ? 'cv-tb__cell--ins' : undefined)

  const flatHeading = (
    <tr>
      {diff.columns.map((col, i) => {
        const leaf = (col.new ?? col.old)!
        const group = groupLabel(col.new ? after : before, leaf)
        const label = (column: TableColumn | null, spec: TableSpec) => (column ? [groupLabel(spec, column), column.label].filter(Boolean).join(' – ') : '')
        return (
          <th key={leaf.id ?? i} scope="col" className={stateClass(col.state)} title={group}>
            {col.state === 'same' ? <Changed before={label(col.old, before)} after={label(col.new, after)} /> : label(col.new ?? col.old, col.new ? after : before)}
          </th>
        )
      })}
    </tr>
  )
  const leveledHeading = header(after).map((line, r) => (
    <tr key={r}>
      {line.map((head) => {
        const old = head.at[1] === null ? before.columns[head.at[0]] : before.columns[head.at[0]]?.children?.[head.at[1]]
        return (
          <th key={head.at.join('.')} scope="col" colSpan={head.colSpan} rowSpan={head.rowSpan}>
            <Changed before={old?.label ?? ''} after={head.label} />
          </th>
        )
      })}
    </tr>
  ))

  return (
    <div className="cv-tb-wrap">
      <table className="cv-tb cv-tb--diff">
        <thead>{diff.reshaped ? flatHeading : leveledHeading}</thead>
        <tbody>
          {diff.rows.map((row, r) => {
            const shown = (row.new ?? row.old)!
            if (shown.type === 'section') {
              const s = row.state
              return (
                <tr key={shown.id ?? r} className="cv-tb__row--section">
                  <td colSpan={diff.columns.length} className={classes('cv-tb__cell', stateClass(s))}>
                    {s === 'same' ? <Changed before={cellOf(row.old!, 0)} after={cellOf(row.new!, 0)} /> : s === 'removed' ? <del>{cellOf(shown, 0)}</del> : cellOf(shown, 0)}
                  </td>
                </tr>
              )
            }
            return (
              <tr key={shown.id ?? r} className={`cv-tb__row--${shown.type}`}>
                {diff.columns.map((col, c) => {
                  const s = state(row.state, col.state)
                  const before = row.old ? cellOf(row.old, col.oldIndex) : ''
                  const now = row.new ? cellOf(row.new, col.newIndex) : ''
                  const changed = s === 'same' && before !== now
                  return (
                    <td key={c} className={classes('cv-tb__cell', stateClass(s), changed && 'cv-tb__cell--chg', hasGap(s === 'removed' ? before : now) && 'cv-tb__cell--gap')}
                        style={{ textAlign: alignOf(col) }}>
                      {s === 'removed' ? <del>{before}</del> : s === 'added' ? now : <Changed before={before} after={now} />}
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
