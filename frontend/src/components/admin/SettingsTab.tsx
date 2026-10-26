import { useState } from 'react'
import { adminApi, type SaveSettingsResult } from '../../api'
import { useAsyncData } from '../../hooks/useAsyncData'
import { formatNumber } from '../../lib/format'
import { Alert } from '../Alert'
import { Button } from '../Button'
import { ConfirmDialog } from '../ConfirmDialog'
import { Spinner } from '../Spinner'
import { useToast } from '../Toast'
import { SettingsSectionCard } from './SettingsSectionCard'

/** "Hệ thống": model and storage configuration generated from GET /api/admin/settings, with the re-index prompt. */
export function SettingsTab() {
  const notify = useToast()
  const { data, error, loading, reload, setData } = useAsyncData((signal) => adminApi.getSettings(signal), [], {
    pollMs: 3000,
    shouldPoll: (overview) => overview.pending_jobs > 0,
  })
  // Bumped per section after a save so its form re-reads the saved values.
  const [versions, setVersions] = useState<Record<string, number>>({})
  const [reindexNeeded, setReindexNeeded] = useState(false)
  const [confirmReindex, setConfirmReindex] = useState(false)

  const saved = (sectionKey: string, result: SaveSettingsResult) => {
    if (data) setData({ ...data, ...result.settings })
    setVersions((current) => ({ ...current, [sectionKey]: (current[sectionKey] ?? 0) + 1 }))
    if (result.reindex_required) setReindexNeeded(true)
    reload() // the save response does not carry the job queue length
  }

  const reindex = async () => {
    const { queued } = await adminApi.reindexAll()
    notify(`Đã đưa ${formatNumber(queued)} văn bản vào hàng đợi lập chỉ mục lại.`)
    setReindexNeeded(false)
    setConfirmReindex(false)
    reload()
  }

  if (error && !data) {
    return <Alert kind="error" title="Không tải được cấu hình" action={<Button onClick={reload}>Thử lại</Button>}>{error.message}</Alert>
  }
  if (!data) return <div className="page-loading">{loading && <Spinner label="Đang tải cấu hình" size={24} />}</div>

  return (
    <div className="settings">
      {reindexNeeded && (
        <Alert
          kind="warning"
          title="Cần lập chỉ mục lại toàn bộ kho"
          action={<Button variant="primary" onClick={() => setConfirmReindex(true)}>Lập chỉ mục lại toàn bộ kho</Button>}
        >
          Model embedding hoặc số chiều vector vừa thay đổi nên các vector đã lưu không còn khớp với model mới. Cho đến khi lập chỉ mục lại,
          tìm kiếm theo ngữ nghĩa có thể thiếu kết quả; việc này chạy nền và có thể mất nhiều thời gian với kho lớn.
        </Alert>
      )}
      {data.pending_jobs > 0 && (
        <p className="settings__jobs" role="status">
          <Spinner size={14} />Hàng đợi xử lý: {formatNumber(data.pending_jobs)} tác vụ đang chờ hoặc đang chạy.
        </p>
      )}
      {data.sections.map((section) => (
        <SettingsSectionCard key={`${section.key}:${versions[section.key] ?? 0}`} section={section} onSaved={saved} />
      ))}

      {confirmReindex && (
        <ConfirmDialog title="Lập chỉ mục lại toàn bộ kho" confirmLabel="Lập chỉ mục lại" onCancel={() => setConfirmReindex(false)} onConfirm={reindex}>
          <p>Mọi văn bản trong kho sẽ được xử lý và lập chỉ mục lại bằng cấu hình embedding hiện tại. Quá trình chạy nền, bạn có thể theo dõi số tác vụ còn lại ở đầu trang.</p>
        </ConfirmDialog>
      )}
    </div>
  )
}
