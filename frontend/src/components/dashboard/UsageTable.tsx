import { useMemo, useState } from 'react'
import type { UnitUsage } from '../../api'
import { Icon } from '../Icon'
import { Sparkline } from './charts/Sparkline'
import { full } from './charts/scale'

type SortKey = 'name' | 'users' | 'questions' | 'uploads' | 'moderation'

const COLUMNS: { key: SortKey; label: string; numeric?: boolean }[] = [
  { key: 'name', label: 'Đơn vị' },
  { key: 'users', label: 'Người dùng', numeric: true },
  { key: 'questions', label: 'Câu hỏi', numeric: true },
  { key: 'uploads', label: 'Văn bản tải lên', numeric: true },
  { key: 'moderation', label: 'Vi phạm', numeric: true },
]
const FOLDED = 12

interface UsageTableProps {
  rows: UnitUsage[]
  days: number
}

/** Per-unit usage in the period: sortable columns, a sparkline of questions per day, folded to the busiest units. */
export function UsageTable({ rows, days }: UsageTableProps) {
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: 'questions', desc: true })
  const [all, setAll] = useState(false)
  const sorted = useMemo(() => {
    const factor = sort.desc ? -1 : 1
    return [...rows].sort((a, b) => {
      const diff = sort.key === 'name' ? a.name.localeCompare(b.name, 'vi') : a[sort.key] - b[sort.key]
      return diff * factor || b.questions - a.questions || a.name.localeCompare(b.name, 'vi')
    })
  }, [rows, sort])
  const shown = all ? sorted : sorted.slice(0, FOLDED)
  const click = (key: SortKey) => setSort((current) => (current.key === key ? { key, desc: !current.desc } : { key, desc: key !== 'name' }))

  return (
    <>
      <div className="usage">
        <table className="usage__table">
          <caption className="sr-only">Sử dụng theo đơn vị trong {days} ngày qua</caption>
          <thead>
            <tr>
              {COLUMNS.map((column) => (
                <th key={column.key} scope="col" className={column.numeric ? 'num' : undefined}
                    aria-sort={sort.key === column.key ? (sort.desc ? 'descending' : 'ascending') : 'none'}>
                  <button type="button" className="usage__sort" onClick={() => click(column.key)}>
                    {column.label}
                    <Icon name={sort.key === column.key ? (sort.desc ? 'arrowDown' : 'arrowUp') : 'chevronsUpDown'} size={14} />
                  </button>
                </th>
              ))}
              <th scope="col" className="usage__trend">Câu hỏi theo ngày</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((row) => (
              <tr key={row.unit_id}>
                <th scope="row">
                  <span className="usage__name">{row.name}</span>
                  {row.branch && row.branch !== row.name && <span className="usage__branch">{row.branch}</span>}
                </th>
                <td className="num tnum">{row.active_users}<span className="usage__of">/{row.users}</span></td>
                <td className="num tnum">{full(row.questions)}</td>
                <td className="num tnum">{full(row.uploads)}</td>
                <td className={row.moderation > 0 ? 'num tnum usage__flag' : 'num tnum'}>{full(row.moderation)}</td>
                <td className="usage__trend"><Sparkline values={row.series} label={`${full(row.questions)} câu hỏi trong ${days} ngày`} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="usage__foot">
        <span>Người dùng: số tài khoản hoạt động / tổng số tài khoản của đơn vị.</span>
        {sorted.length > FOLDED && (
          <button type="button" className="linklike" onClick={() => setAll((value) => !value)} aria-expanded={all}>
            {all ? 'Thu gọn' : `Xem tất cả ${sorted.length} đơn vị`}
          </button>
        )}
      </p>
    </>
  )
}
