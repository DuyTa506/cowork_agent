import type { CheckFile, FixResult } from '../../api/formatCheck'
import { Button } from '../Button'
import { Icon } from '../Icon'
import { DOWNLOADS } from './ActionBar'
import { Notice } from './Notice'

interface FixOutcomeProps {
  outcome: FixResult
  /** Counts of the original file. */
  before: { format: number; spelling: number }
  /** Items by id, to name the ones that failed. */
  items: Map<string, { label: string; found?: string }>
  busy: boolean
  onDownload: (file: CheckFile) => void
}

function Delta({ label, from, to }: { label: string; from: number; to: number }) {
  return (
    <div className="check-delta">
      <span className="check-delta__label">{label}</span>
      <span className="check-delta__values tnum">
        <span className="check-delta__from">{from}</span>
        <Icon name="arrowRight" size={16} />
        <b className={to === 0 ? 'check-delta__to check-delta__to--zero' : 'check-delta__to'}>{to}</b>
      </span>
    </div>
  )
}

/** What the last "Sửa" did: how many places changed, errors before and after, downloads, and the edits that could not be applied. */
export function FixOutcome({ outcome, before, items, busy, onDownload }: FixOutcomeProps) {
  const applied = outcome.applied.length
  const describe = (id: string) => {
    const item = items.get(id)
    return item?.found ? `“${item.found}”` : item?.label ?? id
  }
  return (
    <div className="check-outcome">
      <Notice
        tone={applied > 0 ? 'success' : 'warning'}
        icon={applied > 0 ? 'checkCircle' : 'alert'}
        title={applied > 0 ? `Đã sửa ${applied} chỗ` : 'Không có mục nào áp dụng được'}
        actions={
          applied > 0 ? (
            <>
              {DOWNLOADS.map((entry) => (
                <Button
                  key={entry.file}
                  icon="download"
                  variant={entry.file === 'fixed' ? 'primary' : 'default'}
                  disabled={busy}
                  onClick={() => onDownload(entry.file)}
                >
                  {entry.short}
                </Button>
              ))}
            </>
          ) : undefined
        }
      >
        <p>
          Bản đã sửa còn {outcome.after.format} lỗi thể thức và {outcome.after.spelling} lỗi chính tả (bản gốc: {before.format} và {before.spelling}).
        </p>
        <div className="check-delta-row">
          <Delta label="Thể thức" from={before.format} to={outcome.after.format} />
          <Delta label="Chính tả" from={before.spelling} to={outcome.after.spelling} />
        </div>
      </Notice>
      {outcome.failed.length > 0 && (
        <Notice tone="warning" icon="alert" title={`${outcome.failed.length} mục không áp dụng được`}>
          <ul className="check-failed">
            {outcome.failed.map((entry) => (
              <li key={entry.id}>{describe(entry.id)}: {entry.reason}</li>
            ))}
          </ul>
        </Notice>
      )}
    </div>
  )
}
