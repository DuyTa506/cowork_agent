import { useState } from 'react'
import { adminApi, type AuditEntry } from '../../api'
import { useAsyncData } from '../../hooks/useAsyncData'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { formatDateTime } from '../../lib/format'
import { AUDIT_ACTION_LABELS } from '../../lib/labels'
import { Alert } from '../Alert'
import { Button } from '../Button'
import { Chip } from '../Chip'
import { DataTable, type Column } from '../DataTable'
import { EmptyState } from '../EmptyState'
import { Icon } from '../Icon'
import { Spinner } from '../Spinner'
import type { Tone } from '../../lib/labels'
import type { IconName } from '../Icon'

const PAGE_SIZE = 50

const ACTION_STYLE: Record<string, { tone: Tone; icon: IconName }> = {
  'auth.login': { tone: 'green', icon: 'user' },
  'auth.login_failed': { tone: 'red', icon: 'alertCircle' },
  'auth.change_password': { tone: 'amber', icon: 'key' },
  'document.upload': { tone: 'green', icon: 'upload' },
  'document.view': { tone: 'grey', icon: 'eye' },
  'document.download': { tone: 'grey', icon: 'download' },
  'document.update': { tone: 'blue', icon: 'edit' },
  'document.reprocess': { tone: 'blue', icon: 'refresh' },
  'document.delete': { tone: 'red', icon: 'trash' },
  'user.create': { tone: 'blue', icon: 'plus' },
  'user.update': { tone: 'blue', icon: 'edit' },
  'settings.save': { tone: 'amber', icon: 'sliders' },
  'index.rebuild': { tone: 'blue', icon: 'refresh' },
  'format_check.run': { tone: 'grey', icon: 'shield' },
  'format_check.fix': { tone: 'blue', icon: 'edit' },
  'spellcheck.run': { tone: 'grey', icon: 'spellcheck' },
  'spellcheck.fix': { tone: 'blue', icon: 'edit' },
  'moderation.block': { tone: 'red', icon: 'alertCircle' },
  'moderation.warn': { tone: 'amber', icon: 'alertCircle' },
  'moderation.log': { tone: 'grey', icon: 'alertCircle' },
}

const COLUMNS: Column<AuditEntry>[] = [
  { key: 'time', header: 'Thời gian', nowrap: true, render: (entry) => <span className="tnum">{formatDateTime(entry.created_at)}</span> },
  { key: 'user', header: 'Người dùng', nowrap: true, render: (entry) => <strong>{entry.username}</strong> },
  {
    key: 'action',
    header: 'Hành động',
    render: (entry) => {
      const style = ACTION_STYLE[entry.action] ?? { tone: 'grey' as Tone, icon: 'file' as IconName }
      return (
        <span title={entry.action}>
          <Chip tone={style.tone} icon={style.icon}>{AUDIT_ACTION_LABELS[entry.action] ?? entry.action}</Chip>
        </span>
      )
    },
  },
  { key: 'entity', header: 'Đối tượng', render: (entry) => <span className="audit-entity">{entry.entity_type ? `${entry.entity_type} #${entry.entity_id}` : '—'}</span> },
  { key: 'detail', header: 'Chi tiết', render: (entry) => <span className="audit-detail">{entry.detail || '—'}</span> },
  { key: 'ip', header: 'Địa chỉ IP', nowrap: true, render: (entry) => <span className="tnum">{entry.ip_address || '—'}</span> },
]

/** Audit trail, newest first, filtered by action prefix and user and paged with an offset. */
export function AuditTab() {
  const [action, setAction] = useState('')
  const [username, setUsername] = useState('')
  const [offset, setOffset] = useState(0)
  const debouncedAction = useDebouncedValue(action.trim(), 300)
  const debouncedUser = useDebouncedValue(username.trim(), 300)

  const { data, error, loading, reload } = useAsyncData(
    (signal) => adminApi.listAuditLogs({ action: debouncedAction, username: debouncedUser, limit: PAGE_SIZE, offset }, signal),
    [debouncedAction, debouncedUser, offset],
  )

  const page = Math.floor(offset / PAGE_SIZE) + 1
  const hasNext = (data?.length ?? 0) === PAGE_SIZE

  return (
    <div className="card card--flush">
      <form className="audit-filters" role="search" aria-label="Lọc nhật ký" onSubmit={(event) => event.preventDefault()}>
        <label className="audit-filters__field">
          <span className="field__label">Hành động (tiền tố)</span>
          <span className="input-wrap">
            <Icon name="filter" size={18} />
            <input className="input" list="audit-actions" placeholder="Ví dụ: document hoặc settings.save" value={action} onChange={(event) => { setAction(event.target.value); setOffset(0) }} />
          </span>
        </label>
        <datalist id="audit-actions">
          {Object.keys(AUDIT_ACTION_LABELS).map((code) => <option key={code} value={code}>{AUDIT_ACTION_LABELS[code]}</option>)}
        </datalist>
        <label className="audit-filters__field">
          <span className="field__label">Tài khoản</span>
          <span className="input-wrap">
            <Icon name="user" size={18} />
            <input className="input" placeholder="Tên đăng nhập" value={username} onChange={(event) => { setUsername(event.target.value); setOffset(0) }} />
          </span>
        </label>
        <Button icon="refresh" onClick={reload}>Làm mới</Button>
      </form>

      {error && !data && <div className="admin__pad"><Alert kind="error" title="Không tải được nhật ký" action={<Button onClick={reload}>Thử lại</Button>}>{error.message}</Alert></div>}
      {loading && !data && <div className="page-loading"><Spinner label="Đang tải nhật ký" size={24} /></div>}
      {data && data.length === 0 && <EmptyState icon="clipboard" title="Không có bản ghi" description="Không có hoạt động nào khớp điều kiện lọc." />}
      {data && data.length > 0 && <DataTable caption="Nhật ký hoạt động" columns={COLUMNS} rows={data} getKey={(entry) => entry.id} />}
      {data && (offset > 0 || hasNext) && (
        <nav className="pagination" aria-label="Phân trang nhật ký">
          <span>{data.length} bản ghi trên trang này</span>
          <span className="pagination__controls">
            <Button size="sm" icon="chevronLeft" onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))} disabled={offset === 0}>Trước</Button>
            <span className="pagination__page" aria-current="page">Trang {page}</span>
            <Button size="sm" onClick={() => setOffset(offset + PAGE_SIZE)} disabled={!hasNext}>Sau<Icon name="chevronRight" size={16} /></Button>
          </span>
        </nav>
      )}
    </div>
  )
}
