import { useId, useState, type ReactNode } from 'react'
import { Icon } from '../Icon'

export interface TableView {
  headers: string[]
  rows: (string | number)[][]
}

interface ChartCardProps {
  title: string
  /** One line saying what is counted and over which period. */
  subtitle?: string
  /** The same figures as a table: always available, for people who prefer numbers or use a screen reader. */
  table?: TableView
  /** Extra controls on the right of the header (a "xem tất cả" switch). */
  actions?: ReactNode
  wide?: boolean
  children: ReactNode
}

/** A titled card around one chart with a chart/table switch. */
export function ChartCard({ title, subtitle, table, actions, wide, children }: ChartCardProps) {
  const [asTable, setAsTable] = useState(false)
  const id = useId()
  return (
    <section className={wide ? 'dcard dcard--wide' : 'dcard'} aria-labelledby={id}>
      <header className="dcard__head">
        <div className="dcard__titles">
          <h2 className="dcard__title" id={id}>{title}</h2>
          {subtitle && <p className="dcard__sub">{subtitle}</p>}
        </div>
        <div className="dcard__actions">
          {actions}
          {table && (
            <button type="button" className="dcard__switch" aria-pressed={asTable} onClick={() => setAsTable((v) => !v)}>
              <Icon name={asTable ? 'fileBarChart' : 'listChecks'} size={16} />
              {asTable ? 'Biểu đồ' : 'Bảng số liệu'}
            </button>
          )}
        </div>
      </header>
      {asTable && table ? (
        <div className="dcard__table">
          <table>
            <caption className="sr-only">{title}</caption>
            <thead><tr>{table.headers.map((h, i) => <th key={h} scope="col" className={i > 0 ? 'num' : undefined}>{h}</th>)}</tr></thead>
            <tbody>{table.rows.map((row, r) => (
              <tr key={r}>{row.map((cell, c) => (c === 0 ? <th key={c} scope="row">{cell}</th> : <td key={c} className="num tnum">{typeof cell === 'number' ? cell.toLocaleString('vi-VN') : cell}</td>))}</tr>
            ))}</tbody>
          </table>
        </div>
      ) : children}
    </section>
  )
}
