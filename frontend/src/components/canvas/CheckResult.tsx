import type { DraftCheck, DraftFinding, DraftStyleReport, StyleFinding } from '../../api/chat'
import { formatTime } from '../../lib/format'
import { Button } from '../Button'
import { Icon, type IconName } from '../Icon'

interface CheckPanelProps {
  /** The latest result, or null when the check was never run for this draft. */
  check: DraftCheck | null
  /** The draft changed after the check ran. */
  stale: boolean
  checking: boolean
  /** Required fields still empty. */
  missing: number
  onRun: () => void
}

const SEVERITY: Record<string, { label: string; icon: IconName; tone: 'danger' | 'warning' | 'info' }> = {
  error: { label: 'Bắt buộc sửa', icon: 'alertCircle', tone: 'danger' },
  warning: { label: 'Cảnh báo', icon: 'alert', tone: 'warning' },
  info: { label: 'Lưu ý', icon: 'info', tone: 'info' },
}

/** Number that matters on the "Kiểm tra thể thức" button: problems still to fix. */
export const problemCount = (check: DraftCheck): number => check.counts.error + check.counts.warning

function Finding({ finding }: { finding: DraftFinding }) {
  const severity = SEVERITY[finding.severity] ?? SEVERITY.info!
  return (
    <li className={`finding finding--${severity.tone}`}>
      <Icon name={severity.icon} size={20} className="finding__icon" />
      <div className="finding__body">
        <p className="finding__msg"><span className="finding__sev">{severity.label}</span>{finding.message}</p>
        {(finding.where || finding.ref) && <p className="finding__where">{[finding.where, finding.ref].filter(Boolean).join(' · ')}</p>}
      </div>
    </li>
  )
}

function StyleReport({ style }: { style: DraftStyleReport }) {
  const items: StyleFinding[] = [
    ...style.wording,
    ...style.sections,
    ...(style.blanks > 0 ? [{ severity: 'info', message: `${style.blanks} chỗ còn dấu '…' cần đồng chí điền.` }] : []),
  ]
  if (items.length === 0) return null
  return (
    <section className="cv-check__style" aria-label="Văn phong">
      <h3 className="cv-check__style-title">Văn phong</h3>
      <ul className="cv-check__list">
        {items.map((item, index) => (
          <Finding key={index} finding={{ severity: item.severity === 'warning' ? 'warning' : 'info', message: item.message, where: item.where ?? '', ref: '' }} />
        ))}
      </ul>
    </section>
  )
}

/** Result of the format check of the DOCX built from the draft (doccheck): counts first, then every finding with its severity. */
export function CheckPanel({ check, stale, checking, missing, onRun }: CheckPanelProps) {
  if (!check) {
    return (
      <div className="cv-side__empty">
        <Icon name="shield" size={28} />
        <p className="cv-side__empty-title">Chưa kiểm tra thể thức</p>
        <p>Hệ thống dựng bản DOCX từ bản dự thảo và đối chiếu với Thông tư 68/2023/TT-BQP.</p>
        <Button variant="primary" icon="shield" loading={checking} onClick={onRun}>Kiểm tra thể thức</Button>
      </div>
    )
  }
  const { counts } = check
  const clean = counts.error + counts.warning === 0
  return (
    <div className="cv-check">
      <div className="cv-check__counts" role="group" aria-label="Tổng hợp kết quả kiểm tra">
        <div className="cv-count cv-count--danger"><b className="tnum">{counts.error}</b><span>Bắt buộc</span></div>
        <div className="cv-count cv-count--warning"><b className="tnum">{counts.warning}</b><span>Cảnh báo</span></div>
        <div className="cv-count cv-count--info"><b className="tnum">{counts.manual}</b><span>Tự kiểm tra</span></div>
      </div>
      <div className="cv-check__meta">
        <span>Kiểm tra lúc {formatTime(check.checked_at)}</span>
        <Button icon="refresh" loading={checking} onClick={onRun}>Kiểm tra lại</Button>
      </div>
      {stale && (
        <p className="cv-check__stale" role="status"><Icon name="alert" size={16} />Bản dự thảo đã thay đổi sau lần kiểm tra này. Kiểm tra lại để cập nhật.</p>
      )}
      {check.findings.length === 0 ? (
        clean && missing === 0 ? (
          <p className="cv-check__ok">
            <Icon name="checkCircle" size={20} />
            Đạt: không phát hiện vấn đề về thể thức.
          </p>
        ) : (
          <p className="cv-check__ok cv-check__ok--note">
            <Icon name={clean ? 'info' : 'alert'} size={20} />
            {clean ? `Không phát hiện lỗi thể thức. Còn ${missing} mục chưa điền, đồng chí nhập trước khi ban hành.` : 'Không có mục chi tiết.'}
          </p>
        )
      ) : (
        <ul className="cv-check__list">
          {check.findings.map((finding, index) => (
            <Finding key={index} finding={finding} />
          ))}
        </ul>
      )}
      {check.style && <StyleReport style={check.style} />}
      {counts.manual > 0 && <p className="cv-check__note">{counts.manual} mục cần đồng chí tự kiểm tra (hệ thống không xác định được).</p>}
      <p className="cv-check__note">Bản xuất DOCX do hệ thống dựng đúng kiểu chữ, cỡ chữ, lề theo mẫu rồi kiểm tra lại trước khi tải.</p>
    </div>
  )
}
