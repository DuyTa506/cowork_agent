import { useEffect, useState, type ReactNode } from 'react'
import { Alert } from '../components/Alert'
import { Avatar } from '../components/Avatar'
import { Badge, Chip, LevelChip, StateChip } from '../components/Chip'
import { Button } from '../components/Button'
import { Checkbox } from '../components/Checkbox'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { DataTable, type Column } from '../components/DataTable'
import { DateInput } from '../components/DateInput'
import { Drawer } from '../components/Drawer'
import { EmptyState, type IllustrationName } from '../components/EmptyState'
import { FileTypeBadge } from '../components/FileTypeBadge'
import { Field } from '../components/Field'
import { DocTypeIcon, Icon, type IconName } from '../components/Icon'
import { IconButton } from '../components/IconButton'
import { Input, Textarea } from '../components/Input'
import { ThemeToggle } from '../components/layout/ThemeToggle'
import { Menu } from '../components/Menu'
import { Modal } from '../components/Modal'
import { PageHeader } from '../components/PageHeader'
import { Pagination } from '../components/Pagination'
import { Progress } from '../components/Progress'
import { Select } from '../components/Select'
import { Skeleton, SkeletonText } from '../components/Skeleton'
import { Spinner } from '../components/Spinner'
import { StatCard } from '../components/StatCard'
import { StatusDot } from '../components/StatusDot'
import { Switch } from '../components/Switch'
import { Tabs, tabPanelProps } from '../components/Tabs'
import { useToast } from '../components/Toast'
import { Tooltip } from '../components/Tooltip'
import { useTheme } from '../hooks/useTheme'
import { usePageMeta } from '../hooks/usePageMeta'

/* Dev-only living style guide at /_ui: every token and component in every state. Not part of the production bundle. */

function Section({ id, title, note, children }: { id: string; title: string; note?: ReactNode; children: ReactNode }) {
  return (
    <section className="sg-section" id={id} aria-labelledby={`${id}-h`}>
      <h2 id={`${id}-h`} className="sg-section__title">{title}</h2>
      {note && <p className="sg-section__note">{note}</p>}
      <div className="sg-section__body">{children}</div>
    </section>
  )
}

function Row({ label, children }: { label?: string; children: ReactNode }) {
  return (
    <div className="sg-row">
      {label && <span className="sg-row__label">{label}</span>}
      <div className="sg-row__items">{children}</div>
    </div>
  )
}

const SWATCHES: { group: string; tokens: string[] }[] = [
  { group: 'Nền và chữ', tokens: ['--bg', '--surface', '--surface-2', '--surface-hover', '--border', '--border-strong', '--text', '--text-2', '--text-3', '--placeholder'] },
  { group: 'Thương hiệu', tokens: ['--brand-950', '--brand-900', '--brand-700', '--primary', '--primary-hover', '--primary-soft', '--accent', '--accent-soft'] },
  { group: 'Trạng thái', tokens: ['--ok', '--ok-soft', '--warn', '--warn-soft', '--danger', '--danger-soft', '--info', '--info-soft', '--neutral', '--neutral-soft'] },
  { group: 'Tài liệu', tokens: ['--desk', '--paper', '--highlight', '--ft-word', '--ft-pdf', '--ft-doc'] },
]

function Swatches() {
  const { theme } = useTheme()
  const [values, setValues] = useState<Record<string, string>>({})
  useEffect(() => {
    const style = getComputedStyle(document.documentElement)
    const next: Record<string, string> = {}
    for (const group of SWATCHES) for (const token of group.tokens) next[token] = style.getPropertyValue(token).trim()
    setValues(next)
  }, [theme])
  return (
    <>
      {SWATCHES.map((group) => (
        <Row key={group.group} label={group.group}>
          {group.tokens.map((token) => (
            <div className="sg-swatch" key={token}>
              <span className="sg-swatch__chip" style={{ background: `var(${token})` }} />
              <code>{token}</code>
              <span className="sg-swatch__value">{values[token]}</span>
            </div>
          ))}
        </Row>
      ))}
    </>
  )
}

interface Demo {
  id: number
  number: string
  title: string
  unit: string
  date: string
  state: 'ready' | 'processing' | 'needs_review' | 'failed' | 'needs_ocr' | 'uploaded'
  secret?: boolean
  type: string
}

const DEMOS: Demo[] = [
  { id: 1, number: '33/QĐ-QK3', title: 'Về việc kiện toàn Ban Chỉ đạo diễn tập khu vực phòng thủ', unit: 'Phòng Tác chiến', date: '13/10/2026', state: 'ready', type: 'Quyết định' },
  { id: 2, number: '45/BC-HC', title: 'Báo cáo kết quả kiểm tra công tác bảo đảm hậu cần quý III', unit: 'Phòng Hậu cần', date: '05/10/2026', state: 'processing', type: 'Báo cáo' },
  { id: 3, number: '31/KH-TC', title: 'Kế hoạch tổ chức huấn luyện năm 2026 cho các đơn vị trực thuộc Bộ Tư lệnh', unit: 'Phòng Tham mưu', date: '—', state: 'needs_review', secret: true, type: 'Kế hoạch' },
  { id: 4, number: '…/CV-PCT', title: 'Công văn đề nghị phối hợp bảo đảm kỹ thuật', unit: 'Phòng Công binh', date: '02/10/2026', state: 'failed', type: 'Công văn' },
]

const COLUMNS: Column<Demo>[] = [
  { key: 'n', header: 'Số, ký hiệu', primary: true, nowrap: true, render: (d) => <><span className="cell-main">{d.number}</span><span className="cell-sub">{d.type}</span></> },
  { key: 't', header: 'Trích yếu', render: (d) => <span className="cell-clamp">{d.title}</span> },
  { key: 'u', header: 'Đơn vị', hideBelow: 'lg', render: (d) => d.unit },
  { key: 'd', header: 'Ngày', numeric: true, hideBelow: 'md', nowrap: true, render: (d) => d.date },
  { key: 's', header: 'Trạng thái', render: (d) => <span className="hstack"><StateChip state={d.state} />{d.secret && <LevelChip level="mat" />}</span> },
]

const ILLUSTRATIONS: [IllustrationName, string, string][] = [
  ['documents', 'Kho văn bản còn trống', 'Tải văn bản lên để hệ thống trích xuất và lập chỉ mục.'],
  ['search', 'Không có văn bản phù hợp', 'Thử đổi hoặc bỏ bớt điều kiện lọc.'],
  ['chat', 'Hỏi trợ lý về văn bản', 'Câu trả lời có dẫn nguồn từ văn bản gốc.'],
  ['check', 'Không phát hiện lỗi thể thức', 'Văn bản đạt yêu cầu theo quy định.'],
  ['error', 'Không tải được dữ liệu', 'Kiểm tra mạng nội bộ rồi thử lại.'],
]

const ICON_NAMES: IconName[] = [
  'chat', 'folder', 'shield', 'shieldAlert', 'sliders', 'home', 'bank', 'building', 'users', 'user', 'server', 'tools', 'canvas', 'history', 'inbox', 'layers', 'zap', 'sparkles',
  'file', 'fileX', 'fileCheck', 'fileSearch', 'fileUp', 'gavel', 'calendarRange', 'calendar', 'fileBarChart', 'mail', 'clipboard',
  'upload', 'download', 'search', 'close', 'check', 'plus', 'minus', 'edit', 'trash', 'save', 'copy', 'refresh', 'undo', 'redo', 'send', 'stop', 'clip', 'quote', 'filter', 'logout', 'key', 'lock', 'lockKey', 'eye', 'eyeOff', 'scan', 'externalLink', 'command', 'enter',
  'checkCircle', 'alert', 'alertCircle', 'xCircle', 'info', 'help', 'clock', 'dot', 'spinner', 'offline', 'capsLock',
  'chevronDown', 'chevronUp', 'chevronLeft', 'chevronRight', 'chevronsUpDown', 'arrowLeft', 'arrowRight', 'arrowUp', 'arrowDown', 'arrowUpRight', 'menu', 'more', 'moreVertical', 'panelLeft', 'panelLeftClose', 'panelLeftOpen', 'sun', 'moon', 'zoomIn', 'zoomOut', 'expand',
]

const TAB_ITEMS = [
  { key: 'all', label: 'Tất cả', count: '1.562' },
  { key: 'ready', label: 'Sẵn sàng', count: '1.540' },
  { key: 'review', label: 'Cần rà soát', count: 18 },
  { key: 'failed', label: 'Lỗi', count: 4 },
] as const

/** Living style guide: tokens, type, and every shared component in all of its states. */
export function StyleGuidePage() {
  usePageMeta({ title: 'Bộ giao diện' })
  const notify = useToast()
  const { theme } = useTheme()
  const [tab, setTab] = useState<(typeof TAB_ITEMS)[number]['key']>('all')
  const [checked, setChecked] = useState(true)
  const [partly, setPartly] = useState(false)
  const [on, setOn] = useState(true)
  const [select, setSelect] = useState('a')
  const [date, setDate] = useState('2026-10-13')
  const [modal, setModal] = useState<null | 'modal' | 'confirm' | 'danger'>(null)
  const [drawer, setDrawer] = useState(false)
  const [picked, setPicked] = useState<Set<number>>(new Set([2]))
  const [open, setOpen] = useState<number | null>(3)
  const [stat, setStat] = useState('all')
  const [offset, setOffset] = useState(20)
  const [progress, setProgress] = useState(42)

  return (
    <div className="sg" data-theme-label={theme}>
      <header className="sg-top">
        <div className="sg-top__title">
          <img src="/logo-128.png" width={32} height={32} alt="" />
          <div>
            <h1>QK3 Documents · Bộ giao diện</h1>
            <p>Tokens và thành phần dùng chung. Chỉ có khi chạy <code>npm run dev</code>.</p>
          </div>
        </div>
        <nav className="sg-top__nav" aria-label="Các mục">
          {['color', 'type', 'buttons', 'forms', 'status', 'feedback', 'data', 'overlays', 'empty', 'icons'].map((id) => (
            <a key={id} href={`#${id}`}>{id}</a>
          ))}
        </nav>
        <ThemeToggle />
      </header>

      <main className="sg-main" id="main">
        <Section id="color" title="Màu" note="Bộ token ngữ nghĩa. Sáng và tối cùng tên; không viết mã màu thô trong thành phần.">
          <Swatches />
        </Section>

        <Section id="type" title="Chữ" note="Be Vietnam Pro cho giao diện; Tinos (tương thích Times New Roman) cho trang văn bản.">
          <div className="sg-type">
            <div style={{ font: '700 30px/38px var(--font)' }}>H1 30/38 · Hệ thống AI xử lý văn bản</div>
            <div style={{ font: '600 24px/32px var(--font)' }}>H2 24/32 · Kho văn bản Quân khu 3</div>
            <div style={{ font: '600 20px/28px var(--font)' }}>H3 20/28 · Quyết định về việc kiện toàn</div>
            <div style={{ font: '400 17px/26px var(--font)' }}>Lead 17/26 · Ăn quả nhớ kẻ trồng cây, ưu tiên hậu cần kỹ thuật.</div>
            <div style={{ font: '400 15px/24px var(--font)' }}>Body 15/24 · Đoạn văn trả lời của trợ lý. Thị trường, quyền hạn, điều khoản, thẩm định, phê duyệt.</div>
            <div style={{ font: '400 14px/20px var(--font)' }}>Table 14/20 · ẮẰẲẴẶ ẤẦẨẪẬ ẸẺẼỀỂỄỆ ỈỊỌỎỐỒỔỖỘỚỜỞỠỢ ỤỦỨỪỬỮỰ ỲỴỶỸ Đ</div>
            <div style={{ font: '400 13px/18px var(--font)' }}>Small 13/18 · ăằẳẵặ âấầẩẫậ êếềểễệ ôốồổỗộ ơớờởỡợ ưứừửữự đ</div>
            <div style={{ font: '400 12px/16px var(--font)', color: 'var(--text-3)' }}>Meta 12/16 · Đăng ngày 13/10/2026 · 1.562 văn bản</div>
            <div className="sg-paper">
              <p style={{ textAlign: 'center', fontWeight: 700 }}>CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM</p>
              <p style={{ textAlign: 'center', fontWeight: 700 }}>Độc lập – Tự do – Hạnh phúc</p>
              <p>Căn cứ Luật Ban hành văn bản quy phạm pháp luật; theo đề nghị của Trưởng phòng Tham mưu, Tư lệnh Quân khu quyết định: Điều 1. Kiện toàn Ban Chỉ đạo diễn tập khu vực phòng thủ năm 2026. Đặc biệt, ưu tiên bảo đảm hậu cần, kỹ thuật.</p>
            </div>
          </div>
        </Section>

        <Section id="buttons" title="Nút">
          <Row label="Biến thể">
            <Button variant="primary" icon="plus">Chính</Button>
            <Button>Phụ</Button>
            <Button variant="ghost">Nhạt</Button>
            <Button variant="danger" icon="trash">Xóa</Button>
            <Button variant="danger-solid">Xóa vĩnh viễn</Button>
          </Row>
          <Row label="Cỡ">
            <Button variant="primary" size="sm">Nhỏ 28</Button>
            <Button variant="primary">Vừa 36</Button>
            <Button variant="primary" size="lg">Lớn 44</Button>
            <Button variant="primary" iconEnd="arrowRight">Tiếp theo</Button>
          </Row>
          <Row label="Trạng thái">
            <Button variant="primary" loading>Đang lưu</Button>
            <Button loading>Đang tải</Button>
            <Button variant="primary" disabled>Vô hiệu</Button>
            <Button disabled>Vô hiệu</Button>
            <Button variant="ghost" disabled>Vô hiệu</Button>
          </Row>
          <Row label="Nút biểu tượng">
            <IconButton icon="edit" label="Sửa" />
            <IconButton icon="download" label="Tải về" outline />
            <IconButton icon="trash" label="Xóa" danger />
            <IconButton icon="more" label="Thêm thao tác" size="sm" />
            <IconButton icon="panelLeft" label="Bật tắt khung bên" size="lg" aria-pressed />
            <IconButton icon="refresh" label="Không dùng được" disabled />
            <Tooltip content="Mẹo: nhấn Ctrl+K để tìm nhanh" side="bottom"><Button variant="ghost" icon="help">Di chuột vào đây</Button></Tooltip>
          </Row>
        </Section>

        <Section id="forms" title="Biểu mẫu" note="Nhãn luôn nằm trên; lỗi hiện dưới ô, có biểu tượng và liên kết aria-describedby.">
          <div className="sg-grid">
            <Field label="Số, ký hiệu" hint="Ví dụ: 33/QĐ-QK3">{({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} defaultValue="33/QĐ-QK3" />}</Field>
            <Field label="Tìm kiếm" hideLabel>{({ id }) => <Input id={id} icon="search" placeholder="Số ký hiệu, trích yếu, cơ quan…" />}</Field>
            <Field label="Tên đăng nhập" error="Tên đăng nhập đã tồn tại." required>{({ id, describedBy, invalid }) => <Input id={id} aria-describedby={describedBy} invalid={invalid} defaultValue="chihuy" />}</Field>
            <Field label="Mật khẩu" hint="Ít nhất 8 ký tự.">{({ id, describedBy }) => <Input id={id} aria-describedby={describedBy} type="password" revealable defaultValue="Smoke-Pass-1" />}</Field>
            <Field label="Bị khóa">{({ id }) => <Input id={id} disabled defaultValue="Không sửa được" />}</Field>
            <Field label="Cỡ nhỏ / lớn">
              {({ id }) => (
                <div className="sg-stack">
                  <Input id={id} size="sm" placeholder="Cỡ nhỏ 28" />
                  <Input size="lg" aria-label="Cỡ lớn" icon="user" placeholder="Cỡ lớn 44" />
                </div>
              )}
            </Field>
            <Field label="Loại văn bản">{({ id }) => <Select id={id} value={select} onChange={setSelect} options={[{ value: 'a', label: 'Quyết định' }, { value: 'b', label: 'Kế hoạch' }, { value: 'c', label: 'Báo cáo' }]} />}</Field>
            <Field label="Ngày ban hành" hint="dd/mm/yyyy">{({ id, describedBy }) => <DateInput id={id} aria-describedby={describedBy} value={date} onChange={setDate} />}</Field>
            <Field label="Ghi chú" className="sg-span">{({ id }) => <Textarea id={id} placeholder="Nhập ghi chú…" />}</Field>
          </div>
          <Row label="Chọn">
            <Checkbox checked={checked} onChange={setChecked} label="Đã chọn" />
            <Checkbox checked={false} onChange={() => undefined} label="Chưa chọn" />
            <Checkbox checked={partly} indeterminate onChange={setPartly} label="Chọn một phần" />
            <Checkbox checked disabled onChange={() => undefined} label="Vô hiệu" />
            <Checkbox checked={checked} onChange={setChecked} label="Có mô tả" description="Giải thích ngắn dưới nhãn." />
          </Row>
          <Row label="Công tắc">
            <Switch checked={on} onChange={setOn} label="Soát chính tả tiếng Việt" />
            <Switch checked={!on} onChange={(v) => setOn(!v)} label="Tắt" />
            <Switch checked disabled onChange={() => undefined} label="Vô hiệu" />
            <Switch checked={on} onChange={setOn} label="Có mô tả" description="Gửi nội dung văn bản tới mô hình." />
          </Row>
        </Section>

        <Section id="status" title="Chip, huy hiệu, trạng thái">
          <Row label="Trạng thái văn bản">
            {(['uploaded', 'processing', 'ready', 'needs_review', 'needs_ocr', 'failed'] as const).map((state) => <StateChip key={state} state={state} />)}
          </Row>
          <Row label="Mức độ"><LevelChip level="thuong" /><LevelChip level="mat" /></Row>
          <Row label="Tông">
            <Chip tone="ok" icon="checkCircle">Đạt</Chip>
            <Chip tone="info" icon="info">Gợi ý</Chip>
            <Chip tone="warn" icon="alert">Cảnh báo</Chip>
            <Chip tone="danger" icon="alertCircle">Lỗi</Chip>
            <Chip tone="neutral">Trung tính</Chip>
            <Chip tone="brand" icon="sparkles">Trợ lý</Chip>
            <Chip tone="ok" size="lg" icon="checkCircle">Cỡ lớn 28</Chip>
          </Row>
          <Row label="Huy hiệu"><Badge>12</Badge><Badge tone="brand">Quản trị viên</Badge><Badge tone="ok" icon="check">Hoạt động</Badge><Badge tone="danger">3 lỗi</Badge></Row>
          <Row label="StatusDot"><StatusDot tone="green">Sẵn sàng</StatusDot><StatusDot tone="amber">Cần rà soát</StatusDot><StatusDot tone="red">Lỗi</StatusDot><StatusDot tone="blue">Đang xử lý</StatusDot></Row>
          <Row label="Avatar"><Avatar name="Nguyễn Văn An" size="sm" /><Avatar name="Trần Bình" /><Avatar name="Lê Thị Cẩm Hà" size="lg" /><span className="sg-dark"><Avatar name="Quản Trị" onDark /></span></Row>
          <Row label="Tệp và loại">
            <FileTypeBadge name="a.docx" /><FileTypeBadge name="b.doc" /><FileTypeBadge name="c.pdf" /><FileTypeBadge name="d.txt" size="sm" /><FileTypeBadge name="a.docx" size="lg" />
            <DocTypeIcon type="Quyết định" /><DocTypeIcon type="Kế hoạch" /><DocTypeIcon type="Báo cáo" /><DocTypeIcon type="Công văn" /><DocTypeIcon type="Tờ trình" /><DocTypeIcon type="Quyết định" secret />
          </Row>
        </Section>

        <Section id="feedback" title="Phản hồi">
          <div className="sg-stack">
            <Alert kind="info" title="Thông tin">Văn bản đang được lập chỉ mục; việc này mất khoảng một phút.</Alert>
            <Alert kind="success" title="Đã lưu" action={<Button size="sm">Mở trong kho</Button>}>Bản dự thảo đã được lưu vào kho.</Alert>
            <Alert kind="warning" title="Cần rà soát">Chưa nhận diện được loại văn bản; hãy bổ sung thủ công.</Alert>
            <Alert kind="error" title="Không tải được danh sách" action={<Button size="sm">Thử lại</Button>} onClose={() => undefined}>Không kết nối được máy chủ. Kiểm tra mạng nội bộ rồi thử lại.</Alert>
          </div>
          <Row label="Toast">
            <Button onClick={() => notify('Đã lưu vào kho văn bản.')}>Thành công</Button>
            <Button onClick={() => notify('Không đổi được mật khẩu. Thử lại sau.', 'error', { action: { label: 'Thử lại', onClick: () => notify('Đang thử lại…', 'info') } })}>Lỗi + hành động</Button>
            <Button onClick={() => notify('Có 3 văn bản đang chờ xử lý.', 'info')}>Thông tin</Button>
            <Button onClick={() => notify('Tệp lớn hơn 50 MB sẽ xử lý lâu hơn.', 'warning')}>Cảnh báo</Button>
          </Row>
          <Row label="Tiến độ">
            <Spinner label="Đang tải" /><Spinner size={24} /><Spinner size={32} />
            <div className="sg-w"><Progress value={progress} label="Đang tải lên 3/5 tệp" valueText={`${progress}%`} /></div>
            <div className="sg-w"><Progress label="Đang lập chỉ mục" /></div>
            <Button size="sm" onClick={() => setProgress((p) => (p >= 100 ? 0 : p + 29))}>Tăng</Button>
          </Row>
          <Row label="Skeleton">
            <div className="sg-w"><SkeletonText lines={3} /></div>
            <Skeleton width={48} height={48} circle />
            <Skeleton width={160} height={32} />
          </Row>
        </Section>

        <Section id="data" title="Dữ liệu">
          <Tabs items={[...TAB_ITEMS]} value={tab} onChange={setTab} label="Lọc theo trạng thái" idPrefix="sg-tab" />
          <div {...tabPanelProps('sg-tab', tab)} className="tab-panel sg-stack">
            <div className="stat-grid">
              <StatCard label="Tất cả" value="1.562" icon="folder" hint="Cập nhật 14:05" selected={stat === 'all'} onClick={() => setStat('all')} />
              <StatCard label="Sẵn sàng" value="1.540" icon="checkCircle" tone="ok" hint="98,6% tổng số" selected={stat === 'ready'} onClick={() => setStat('ready')} />
              <StatCard label="Đang xử lý" value="3" icon="spinner" tone="info" selected={stat === 'proc'} onClick={() => setStat('proc')} />
              <StatCard label="Cần rà soát" value="18" icon="alert" tone="warn" selected={stat === 'rev'} onClick={() => setStat('rev')} />
              <StatCard label="Lỗi" value="1" icon="alertCircle" tone="danger" selected={stat === 'err'} onClick={() => setStat('err')} />
              <StatCard label="Đang tải" value="—" loading />
            </div>
            <DataTable
              caption="Văn bản mẫu"
              columns={COLUMNS}
              rows={DEMOS}
              getKey={(d) => d.id}
              selectedKey={open}
              onSelect={(d) => { setOpen(d.id); setDrawer(true) }}
              selection={{ selected: picked, onChange: setPicked }}
              rowLabel={(d) => d.number}
              footer={<Pagination className="table-foot" offset={offset} limit={20} total={1562} noun="văn bản" onOffsetChange={setOffset} />}
            />
            <div className="sg-grid sg-grid--2">
              <DataTable caption="Đang tải" columns={COLUMNS} rows={[]} getKey={(d) => d.id} loading skeletonRows={3} />
              <DataTable caption="Trống" columns={COLUMNS} rows={[]} getKey={(d) => d.id} empty={<EmptyState compact illustration="search" title="Không có văn bản phù hợp" description="Thử bỏ bớt điều kiện lọc." action={<Button size="sm">Xóa bộ lọc</Button>} />} />
            </div>
          </div>
        </Section>

        <Section id="overlays" title="Lớp phủ" note="Drawer cho chi tiết bản ghi; Modal cho quyết định ngắn hoặc biểu mẫu nhỏ; ConfirmDialog cho thao tác không hoàn tác.">
          <Row>
            <Button onClick={() => setModal('modal')}>Mở hộp thoại</Button>
            <Button onClick={() => setModal('confirm')}>Xác nhận</Button>
            <Button variant="danger" onClick={() => setModal('danger')}>Xác nhận xóa</Button>
            <Button onClick={() => setDrawer(true)}>Mở ngăn chi tiết</Button>
            <Menu
              label="Thao tác mẫu"
              items={[
                { key: 'h', type: 'header', title: 'Quản Trị Viên', subtitle: 'Quân khu 3' },
                { key: 'a', label: 'Mở trang riêng', icon: 'externalLink', onSelect: () => notify('Mở trang riêng', 'info') },
                { key: 'b', label: 'Tải tệp gốc', icon: 'download', hint: 'Ctrl+D', onSelect: () => notify('Đang tải…', 'info') },
                { key: 'c', label: 'Không dùng được', icon: 'lock', disabled: true, onSelect: () => undefined },
                { key: 's', type: 'separator' },
                { key: 'd', label: 'Xóa văn bản', icon: 'trash', danger: true, onSelect: () => setModal('danger') },
              ]}
              trigger={(props, { open: isOpen }) => (
                <Button {...props} iconEnd="chevronDown" aria-expanded={isOpen}>Thao tác</Button>
              )}
            />
          </Row>
          <p className="sg-section__note">Bảng lệnh: nhấn <kbd>Ctrl</kbd> <kbd>K</kbd> hoặc <kbd>/</kbd> trong khung ứng dụng (không có ở trang này).</p>
        </Section>

        <Section id="empty" title="Trạng thái trống">
          <div className="sg-empties">
            {ILLUSTRATIONS.map(([name, title, text]) => (
              <div className="sg-empty" key={name}><EmptyState illustration={name} title={title} description={text} action={<Button size="sm" variant={name === 'error' ? 'primary' : 'default'}>{name === 'error' ? 'Thử lại' : 'Hành động'}</Button>} compact /></div>
            ))}
          </div>
        </Section>

        <Section id="icons" title="Biểu tượng" note="lucide, nét 1,75; 18 px trong điều khiển, 20 px trong điều hướng.">
          <div className="sg-icons">
            {ICON_NAMES.map((name) => (
              <div className="sg-icon" key={name}><Icon name={name} size={20} /><span>{name}</span></div>
            ))}
          </div>
        </Section>

        <PageHeader title="Tiêu đề trang" description="Một câu mô tả, tối đa một nút chính ở bên phải.">
          <Button>Phụ</Button>
          <Button variant="primary" icon="upload">Tải văn bản lên</Button>
        </PageHeader>
      </main>

      {modal === 'modal' && (
        <Modal title="Đổi tên cuộc trò chuyện" description="Tên mới hiện trong danh sách bên trái." onClose={() => setModal(null)} footer={<><Button onClick={() => setModal(null)}>Hủy</Button><Button variant="primary" onClick={() => setModal(null)}>Lưu</Button></>}>
          <Field label="Tên mới">{({ id }) => <Input id={id} defaultValue="Kế hoạch huấn luyện 2026" data-autofocus />}</Field>
        </Modal>
      )}
      {modal === 'confirm' && <ConfirmDialog title="Xử lý lại văn bản?" confirmLabel="Xử lý lại" onConfirm={() => new Promise<void>((resolve) => window.setTimeout(resolve, 800)).then(() => setModal(null))} onCancel={() => setModal(null)}>Hệ thống sẽ trích xuất lại trường và lập chỉ mục lại văn bản 33/QĐ-QK3.</ConfirmDialog>}
      {modal === 'danger' && <ConfirmDialog danger title="Xóa văn bản 33/QĐ-QK3?" confirmLabel="Xóa văn bản" onConfirm={() => setModal(null)} onCancel={() => setModal(null)}>Văn bản và các đoạn đã lập chỉ mục sẽ bị xóa vĩnh viễn. Không thể hoàn tác.</ConfirmDialog>}
      {drawer && (
        <Drawer
          title="33/QĐ-QK3 · Về việc kiện toàn Ban Chỉ đạo"
          subtitle="Phòng Tác chiến · 13/10/2026"
          chips={<><StateChip state="ready" /><LevelChip level="thuong" /></>}
          onClose={() => setDrawer(false)}
          tabs={<Tabs items={[{ key: 'a', label: 'Thông tin' }, { key: 'b', label: 'Xử lý', count: 5 }, { key: 'c', label: 'Nhật ký' }]} value="a" onChange={() => undefined} label="Chi tiết" idPrefix="sg-dr" />}
          footerStart={<Button variant="danger" icon="trash">Xóa</Button>}
          footer={<><Button icon="download">Tải tệp gốc</Button><Button variant="primary" icon="eye">Xem văn bản</Button></>}
        >
          <SkeletonText lines={4} />
          <Alert kind="warning" title="Cần rà soát">Chưa nhận diện được người ký.</Alert>
          <SkeletonText lines={6} />
        </Drawer>
      )}
    </div>
  )
}
