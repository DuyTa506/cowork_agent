import { useMemo, useState } from 'react'
import { adminApi, type Role, type User } from '../../api'
import { useAsyncData } from '../../hooks/useAsyncData'
import { useUnits } from '../../hooks/useUnits'
import { ROLE_LABELS } from '../../lib/labels'
import { Alert } from '../Alert'
import { Button } from '../Button'
import { Chip } from '../Chip'
import { DataTable, type Column } from '../DataTable'
import { EmptyState } from '../EmptyState'
import { Icon, type IconName } from '../Icon'
import { Spinner } from '../Spinner'
import { Badge } from '../StatusDot'
import { UnitTree } from './UnitTree'
import { UserDialog } from './UserDialog'

type Editing = { mode: 'create' } | { mode: 'edit'; user: User }

const ROLE_BADGES: Record<Role, { tone: 'blue' | 'amber' | 'green' | 'grey'; icon: IconName }> = {
  admin: { tone: 'blue', icon: 'shield' },
  commander: { tone: 'amber', icon: 'lockKey' },
  reviewer: { tone: 'green', icon: 'eye' },
  staff: { tone: 'grey', icon: 'user' },
}

/** Accounts table (create / edit) next to the unit tree with the number of accounts in each unit. */
export function UsersTab() {
  const { data, error, loading, reload } = useAsyncData((signal) => adminApi.listUsers(signal), [])
  const { units } = useUnits()
  const [editing, setEditing] = useState<Editing | null>(null)
  const [filter, setFilter] = useState('')

  const perUnit = useMemo(() => {
    const counts = new Map<string, number>()
    for (const user of data ?? []) counts.set(user.unit_id, (counts.get(user.unit_id) ?? 0) + 1)
    return counts
  }, [data])

  const shown = useMemo(() => {
    const needle = filter.trim().toLowerCase()
    if (!needle || !data) return data
    return data.filter((user) => [user.username, user.full_name, user.unit_name, ROLE_LABELS[user.role]].some((text) => text.toLowerCase().includes(needle)))
  }, [data, filter])

  const columns: Column<User>[] = [
    {
      key: 'username',
      header: 'Tài khoản',
      render: (user) => (
        <span className="user-cell">
          <span className="user-cell__avatar" aria-hidden="true">{(user.full_name || user.username).trim().charAt(0).toUpperCase()}</span>
          <span className="user-cell__text">
            <strong>{user.username}</strong>
            <span>{user.full_name || '—'}</span>
          </span>
        </span>
      ),
    },
    { key: 'unit', header: 'Đơn vị', render: (user) => user.unit_name || user.unit_id },
    { key: 'role', header: 'Vai trò', nowrap: true, render: (user) => <Badge tone={ROLE_BADGES[user.role].tone} icon={ROLE_BADGES[user.role].icon}>{ROLE_LABELS[user.role]}</Badge> },
    {
      key: 'active',
      header: 'Trạng thái',
      nowrap: true,
      render: (user) => (user.is_active ? <Chip tone="green" icon="checkCircle">Hoạt động</Chip> : <Chip tone="grey" icon="lock">Đã khóa</Chip>),
    },
    {
      key: 'edit',
      header: '',
      nowrap: true,
      render: (user) => <Button size="sm" icon="edit" onClick={() => setEditing({ mode: 'edit', user })} aria-label={`Sửa tài khoản ${user.username}`}>Sửa</Button>,
    },
  ]

  return (
    <div className="admin-users">
      <section className="card card--flush admin-users__main" aria-label="Tài khoản">
        <div className="card__head">
          <span className="input-wrap admin-users__search">
            <Icon name="search" size={18} />
            <input className="input" type="search" placeholder="Lọc theo tên, đơn vị, vai trò…" aria-label="Lọc tài khoản" value={filter} onChange={(event) => setFilter(event.target.value)} />
          </span>
          <Button variant="primary" icon="plus" onClick={() => setEditing({ mode: 'create' })}>Thêm tài khoản</Button>
        </div>
        {error && !data && <div className="admin__pad"><Alert kind="error" title="Không tải được danh sách tài khoản" action={<Button onClick={reload}>Thử lại</Button>}>{error.message}</Alert></div>}
        {loading && !data && <div className="page-loading"><Spinner label="Đang tải tài khoản" size={24} /></div>}
        {shown && shown.length > 0 && <DataTable caption="Danh sách tài khoản" columns={columns} rows={shown} getKey={(user) => user.id} />}
        {shown && shown.length === 0 && <EmptyState icon="users" title="Không có tài khoản" description="Không có tài khoản nào khớp với bộ lọc." />}
        {data && <div className="pagination"><span>{shown && shown.length < data.length ? `${shown.length} / ${data.length} tài khoản` : `${data.length} tài khoản`}</span></div>}
      </section>

      <section className="card card--flush admin-users__units" aria-label="Sơ đồ đơn vị">
        <div className="card__head"><h3 className="section-label">Sơ đồ đơn vị</h3><span className="sub">Số tài khoản</span></div>
        <UnitTree units={units} counts={perUnit} />
      </section>

      {editing && (
        <UserDialog user={editing.mode === 'edit' ? editing.user : undefined} onClose={() => setEditing(null)} onSaved={reload} />
      )}
    </div>
  )
}
