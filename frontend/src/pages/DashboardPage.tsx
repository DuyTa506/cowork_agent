import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { statsApi, ApiError, type Stats } from '../api'
import { STATS_PERIODS } from '../api/stats'
import { Alert } from '../components/Alert'
import { Button } from '../components/Button'
import { BarList } from '../components/dashboard/charts/BarList'
import { Donut, type DonutSlice } from '../components/dashboard/charts/Donut'
import { full, longDay, longMonth, shortDay, shortMonth } from '../components/dashboard/charts/scale'
import { TimeChart } from '../components/dashboard/charts/TimeChart'
import { ChartCard } from '../components/dashboard/ChartCard'
import { UsageTable } from '../components/dashboard/UsageTable'
import { EmptyState } from '../components/EmptyState'
import { Icon } from '../components/Icon'
import { PageHeader } from '../components/PageHeader'
import { Skeleton } from '../components/Skeleton'
import { StatCard } from '../components/StatCard'
import { useAsyncData } from '../hooks/useAsyncData'
import { useDocumentTitle } from '../hooks/useDocumentTitle'
import { formatDateTime } from '../lib/format'

const TOP_UNITS = 10
const STATE_COLORS: Record<string, string> = {
  ready: 'var(--viz-good)', needs_review: 'var(--viz-warning)', needs_ocr: 'var(--viz-s2)', failed: 'var(--viz-critical)',
  uploaded: 'var(--viz-muted)', processing: 'var(--viz-s1)',
}
const ACTION_ICONS = { block: 'xCircle', warn: 'alert', log: 'info' } as const

const percent = (part: number, total: number): string => (total ? `${(Math.round((part / total) * 1000) / 10).toLocaleString('vi-VN')}%` : '0%')
const kho = (params: Record<string, string>): string => `/kho?${new URLSearchParams(params).toString()}`

/** "Thống kê" (administrators and commanders): what the document store holds and how the units use the assistant. */
export function DashboardPage() {
  useDocumentTitle('Thống kê')
  const [params, setParams] = useSearchParams()
  const requested = Number(params.get('ngay'))
  const days = (STATS_PERIODS as readonly number[]).includes(requested) ? requested : 30
  const { data, error, loading, reload } = useAsyncData((signal) => statsApi.getStats(days, signal), [days])
  const setDays = (value: number) => setParams((current) => { const next = new URLSearchParams(current); next.set('ngay', String(value)); return next }, { replace: true })

  return (
    <div className="page page--wide dash">
      <PageHeader title="Thống kê" description={data ? scopeText(data) : 'Văn bản trong kho và mức sử dụng của các đơn vị.'}>
        <div className="seg" role="radiogroup" aria-label="Khoảng thời gian">
          {STATS_PERIODS.map((value) => (
            <button key={value} type="button" role="radio" aria-checked={value === days} className={value === days ? 'seg__item seg__item--on' : 'seg__item'} onClick={() => setDays(value)}>
              {value} ngày
            </button>
          ))}
        </div>
        <Button icon="refresh" onClick={reload} loading={loading && data !== null}>Làm mới</Button>
      </PageHeader>

      {error && !data && (
        <Alert kind="error" title="Không tải được số liệu thống kê" action={<Button onClick={reload}>Thử lại</Button>}>
          {error instanceof ApiError && error.status === 403 ? 'Trang này chỉ dành cho quản trị viên và chỉ huy.' : error.message}
        </Alert>
      )}
      {!data && !error && <DashboardSkeleton />}
      {data && data.totals.documents === 0 && data.usage_by_unit.length === 0 && (
        <EmptyState illustration="documents" title="Chưa có số liệu" description="Khi có văn bản trong kho và người dùng bắt đầu hỏi trợ lý, thống kê sẽ hiện ở đây." />
      )}
      {data && (data.totals.documents > 0 || data.usage_by_unit.length > 0) && <Dashboard data={data} days={days} refreshing={loading} />}
    </div>
  )
}

function scopeText(data: Stats): string {
  const where = data.scope.everything ? 'toàn Quân khu' : data.scope.unit_name
  return `Phạm vi: ${where}. Số liệu văn bản tính cả văn bản mật (chỉ đếm, không hiện nội dung); cập nhật ${formatDateTime(data.generated_at)}.`
}

function Dashboard({ data, days, refreshing }: { data: Stats; days: number; refreshing: boolean }) {
  const { totals } = data
  const [allUnits, setAllUnits] = useState(false)
  const units = useMemo(() => data.by_unit.filter((u) => u.count > 0), [data.by_unit])
  const slices: DonutSlice[] = data.by_state.map((s) => ({ key: s.key, label: s.label, value: s.count, color: STATE_COLORS[s.key] ?? 'var(--viz-muted)' }))
  const typeItems = data.by_type.map((t) => ({ key: t.key, label: t.label, value: t.count, href: t.key === '-' || t.key === 'other' ? undefined : kho({ tp: t.key }) }))
  const unitItems = (allUnits ? units : units.slice(0, TOP_UNITS)).map((u) => ({ key: u.unit_id, label: u.name, value: u.count, note: u.branch !== u.name ? u.branch : '', href: kho({ u: u.unit_id }) }))

  return (
    <div className={refreshing ? 'dash__body dash__body--busy' : 'dash__body'}>
      <div className="stat-grid dash__kpis">
        <StatCard label="Tổng số văn bản" value={full(totals.documents)} icon="folder" hint={`${full(totals.secret)} mật · ${full(totals.scanned)} bản scan`} />
        <StatCard label="Sẵn sàng" value={full(totals.ready)} icon="checkCircle" tone="ok" hint={`${percent(totals.ready, totals.documents)} tổng số`} />
        <StatCard label="Cần xem lại" value={full(totals.needs_review)} icon="alert" tone="warn" hint={totals.failed ? `${full(totals.failed)} không đọc được` : 'Thiếu loại hoặc trích yếu'} />
        <StatCard label="Câu hỏi trong tháng" value={full(totals.questions_month)} icon="chat" tone="info" hint={`${full(totals.questions_period)} trong ${days} ngày qua`} />
        <StatCard label="Người dùng hoạt động" value={full(totals.active_users)} icon="users" hint={`trên ${full(totals.users)} tài khoản · ${days} ngày`} />
        <StatCard label="Đề xuất trên Canvas" value={full(data.canvas.proposals)} icon="canvas"
                  hint={data.canvas.proposals
                    ? `${percent(data.canvas.accepted, data.canvas.proposals)} chấp nhận · ${percent(data.canvas.edited_after, data.canvas.accepted)} phải sửa lại`
                    : `Chưa có trong ${days} ngày`} />
      </div>

      <div className="dash__grid">
        <ChartCard title="Văn bản theo loại" subtitle="Số văn bản trong kho; bấm tên để mở kho đã lọc"
                   table={{ headers: ['Loại', 'Số văn bản'], rows: data.by_type.map((t) => [t.label, t.count]) }}>
          <BarList items={typeItems} label="Văn bản theo loại" unit="văn bản" />
        </ChartCard>

        <ChartCard title="Tình trạng xử lý" subtitle="Văn bản theo trạng thái trong kho"
                   table={{ headers: ['Trạng thái', 'Số văn bản'], rows: data.by_state.map((s) => [s.label, s.count]) }}>
          <Donut slices={slices} centerLabel="văn bản" label="Tình trạng xử lý" />
        </ChartCard>

        <ChartCard title="Văn bản theo đơn vị" subtitle={`${units.length} đơn vị có văn bản; mỗi văn bản tính vào đơn vị lưu nó`}
                   table={{ headers: ['Đơn vị', 'Nhánh', 'Số văn bản'], rows: units.map((u) => [u.name, u.branch, u.count]) }}
                   actions={units.length > TOP_UNITS ? (
                     <button type="button" className="linklike" aria-expanded={allUnits} onClick={() => setAllUnits((v) => !v)}>{allUnits ? 'Thu gọn' : `Xem tất cả ${units.length}`}</button>
                   ) : undefined}>
          <BarList items={unitItems} label="Văn bản theo đơn vị" unit="văn bản" />
        </ChartCard>

        <ChartCard title="Câu hỏi gửi trợ lý theo ngày" subtitle={`${full(totals.questions_period)} câu hỏi trong ${days} ngày qua`}
                   table={{ headers: ['Ngày', 'Câu hỏi'], rows: data.questions_by_day.map((d) => [longDay(d.day), d.count]) }}>
          <TimeChart kind="line" unit="câu hỏi" label={`Câu hỏi gửi trợ lý theo ngày, ${days} ngày qua`}
                     points={data.questions_by_day.map((d) => ({ tick: shortDay(d.day), title: longDay(d.day), value: d.count }))} />
        </ChartCard>

        <ChartCard title="Văn bản tải lên theo tháng" subtitle="12 tháng gần nhất"
                   table={{ headers: ['Tháng', 'Số văn bản'], rows: data.uploads_by_month.map((m) => [longMonth(m.key), m.count]) }}>
          <TimeChart kind="columns" unit="văn bản" label="Văn bản tải lên theo tháng, 12 tháng gần nhất"
                     points={data.uploads_by_month.map((m) => ({ tick: shortMonth(m.key), title: longMonth(m.key), value: m.count }))} />
        </ChartCard>

        <ChartCard title="Văn bản theo năm ban hành" subtitle="Theo ngày ghi trên văn bản (không tính bản nháp chưa có ngày)"
                   table={{ headers: ['Năm', 'Số văn bản'], rows: data.by_issued_year.map((y) => [y.label, y.count]) }}>
          <TimeChart kind="columns" unit="văn bản" label="Văn bản theo năm ban hành"
                     points={data.by_issued_year.map((y) => ({ tick: y.label, title: `Năm ${y.label}`, value: y.count }))} />
        </ChartCard>

        <ChartCard title="Chủ đề phổ biến" subtitle="Thẻ chủ đề hệ thống tự gắn (một văn bản có thể có nhiều thẻ)"
                   table={{ headers: ['Thẻ', 'Số văn bản'], rows: data.by_tag.map((t) => [t.label, t.count]) }}>
          <BarList items={data.by_tag.slice(0, 10).map((t) => ({ key: t.key, label: t.label, value: t.count, href: kho({ tag: t.key }) }))} label="Chủ đề phổ biến" unit="văn bản" />
        </ChartCard>

        <ChartCard title="Kiểm duyệt đầu vào" subtitle={`Câu hỏi có lời lẽ vi phạm trong ${days} ngày qua`}
                   table={{ headers: ['Mức xử lý', 'Số lần'], rows: data.moderation_by_action.map((a) => [a.label, a.count]) }}>
          {totals.moderation_period === 0 ? (
            <p className="dash__none"><Icon name="checkCircle" size={18} /> Không có tin nhắn nào bị ghi nhận.</p>
          ) : (
            <>
              <ul className="modstats" aria-label="Số lần theo mức xử lý">
                {data.moderation_by_action.map((a) => (
                  <li key={a.key} className={`modstats__item modstats__item--${a.key}`}>
                    <Icon name={ACTION_ICONS[a.key as keyof typeof ACTION_ICONS] ?? 'info'} size={18} />
                    <span className="modstats__num tnum">{full(a.count)}</span>
                    <span className="modstats__label">{a.label}</span>
                  </li>
                ))}
              </ul>
              <ol className="modlist" aria-label="Các lần gần đây">
                {data.moderation_recent.map((e, i) => (
                  <li key={`${e.at}${i}`}>
                    <span className="modlist__time tnum">{formatDateTime(e.at)}</span>
                    <span className="modlist__who">{e.username}</span>
                    <span className="modlist__unit">{e.unit_name}</span>
                    <span className={`modlist__tag modlist__tag--${e.action}`}>{{ block: 'Chặn', warn: 'Cảnh báo', log: 'Ghi nhận' }[e.action]}</span>
                  </li>
                ))}
              </ol>
              <p className="dash__hint">Chi tiết từng lần xem ở Quản trị → Nhật ký (lọc “moderation”).</p>
            </>
          )}
        </ChartCard>

        <ChartCard wide title="Sử dụng theo đơn vị" subtitle={`Trong ${days} ngày qua; bấm tiêu đề cột để sắp xếp`}
                   table={{ headers: ['Đơn vị', 'Tài khoản hoạt động', 'Tài khoản', 'Câu hỏi', 'Văn bản tải lên', 'Vi phạm'],
                            rows: data.usage_by_unit.map((u) => [u.name, u.active_users, u.users, u.questions, u.uploads, u.moderation]) }}>
          <UsageTable rows={data.usage_by_unit} days={days} />
        </ChartCard>
      </div>
    </div>
  )
}

function DashboardSkeleton() {
  return (
    <div className="dash__body" role="status" aria-label="Đang tải số liệu">
      <div className="stat-grid dash__kpis">{Array.from({ length: 6 }, (_, i) => <StatCard key={i} label="Đang tải" value="" loading />)}</div>
      <div className="dash__grid">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="dcard"><Skeleton width="45%" height={18} /><div className="dash__skel">{Array.from({ length: 5 }, (_, j) => <Skeleton key={j} height={16} width={`${90 - j * 12}%`} />)}</div></div>
        ))}
      </div>
    </div>
  )
}
