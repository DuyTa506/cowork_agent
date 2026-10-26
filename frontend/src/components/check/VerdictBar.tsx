import type { CheckSession } from '../../api/formatCheck'
import { formatFileSize, formatTime } from '../../lib/format'
import { Button } from '../Button'
import { FileTypeBadge } from '../FileTypeBadge'
import { Icon, type IconName } from '../Icon'
import { Select, type SelectOption } from '../Select'
import { Switch } from '../Switch'
import { LEVELS, LEVEL_ORDER, type Level } from './model'

export type LevelFilter = Level | 'all'

interface VerdictBarProps {
  session: CheckSession
  /** Number of findings per level (rows of the list). */
  counts: Record<Level, number>
  /** Findings that can be fixed automatically. */
  fixable: number
  pageCount: number
  checkedAt: string
  filter: LevelFilter
  onFilter: (filter: LevelFilter) => void
  profile: string
  profileOptions: SelectOption[]
  onProfile: (profile: string) => void
  spell: boolean
  onSpell: (spell: boolean) => void
  optionsChanged: boolean
  rechecking: boolean
  disabled: boolean
  onRecheck: () => void
}

/** Plural-free Vietnamese: "9 cảnh báo, 8 lỗi chính tả". */
function restText(counts: Record<Level, number>, skipErrors: boolean): string {
  const parts: string[] = []
  if (!skipErrors && counts.error > 0) parts.push(`${counts.error} lỗi bắt buộc`)
  if (counts.warning > 0) parts.push(`${counts.warning} cảnh báo`)
  if (counts.spelling > 0) parts.push(`${counts.spelling} lỗi chính tả`)
  if (counts.info > 0) parts.push(`${counts.info} lưu ý`)
  return parts.join(', ')
}

/**
 * Top of the result: which file, the verdict in one serif sentence, and the severity counts, which are also the list filter.
 * The check options (rule set, spelling) live here too, because changing them means checking the file again.
 */
export function VerdictBar({
  session, counts, fixable, pageCount, checkedAt, filter, onFilter,
  profile, profileOptions, onProfile, spell, onSpell, optionsChanged, rechecking, disabled, onRecheck,
}: VerdictBarProps) {
  const { result } = session
  const total = LEVEL_ORDER.reduce((sum, level) => sum + counts[level], 0)
  const failed = counts.error > 0
  const isPdf = session.kind === 'pdf'
  const meta = [
    pageCount > 0 ? `${isPdf ? '' : '~'}${pageCount} trang` : null,
    formatFileSize(session.size),
    result.facts.doc_type ? `Nhận dạng: ${result.facts.doc_type}` : null,
    `Kiểm tra lúc ${formatTime(checkedAt)}`,
  ].filter(Boolean) as string[]

  const headline = failed
    ? `Chưa đạt thể thức: ${counts.error} lỗi bắt buộc`
    : 'Đạt thể thức'
  const rest = restText(counts, failed)
  const sub = failed
    ? [rest && `Còn ${rest}.`, fixable > 0 && !isPdf ? `${fixable} mục có thể tự sửa.` : null].filter(Boolean).join(' ')
    : total === 0
      ? `Không phát hiện lỗi thể thức${session.spell ? ' và chính tả' : ''}.`
      : `Không có lỗi bắt buộc. Còn ${rest}.`

  const buttons: { key: LevelFilter; label: string; icon: IconName; tone: string; count: number }[] = [
    { key: 'all', label: 'Tất cả', icon: 'listChecks', tone: 'primary', count: total },
    ...LEVEL_ORDER.map((level) => ({ key: level, label: LEVELS[level].short, icon: LEVELS[level].icon, tone: LEVELS[level].tone, count: counts[level] })),
  ]

  return (
    <section className="check-verdict" aria-label="Kết luận kiểm tra">
      <div className="check-verdict__file">
        <FileTypeBadge name={session.name} size="md" />
        <div className="check-verdict__id">
          <div className="check-verdict__name" title={session.name}>{session.name}</div>
          <div className="check-verdict__meta" title={meta.join(' · ')}>
            {meta.join(' · ')}
          </div>
        </div>
        <div className="check-verdict__opts">
          <label className="check-verdict__field">
            <Select aria-label="Bộ luật thể thức" value={profile} options={profileOptions} onChange={onProfile} disabled={disabled} />
          </label>
          <Switch checked={spell} onChange={onSpell} label="Soát chính tả" disabled={disabled} />
          <Button
            icon="refresh"
            variant={optionsChanged ? 'primary' : 'default'}
            loading={rechecking}
            disabled={disabled}
            onClick={onRecheck}
            title={session.fixed ? 'Kiểm tra lại bản gốc; bản đã sửa hiện có sẽ bị bỏ' : undefined}
          >
            Kiểm tra lại
          </Button>
        </div>
      </div>

      <div className={`check-verdict__main check-verdict__main--${failed ? 'fail' : 'pass'}`}>
        <span className="check-verdict__mark">
          <Icon name={failed ? 'warnOctagon' : 'checkCircle'} size={28} weight="fill" />
        </span>
        <div>
          <h2 className="check-verdict__headline">{headline}</h2>
          {sub && <p className="check-verdict__sub">{sub}</p>}
        </div>
      </div>

      <div className="check-seg" role="group" aria-label="Lọc theo mức độ">
        {buttons.map((button) => {
          const on = filter === button.key
          return (
            <button
              key={button.key}
              type="button"
              className={`check-seg__btn check-seg__btn--${button.tone}${on ? ' is-on' : ''}`}
              aria-pressed={on}
              disabled={button.count === 0 && button.key !== 'all'}
              onClick={() => onFilter(on && button.key !== 'all' ? 'all' : button.key)}
            >
              <Icon name={button.icon} size={18} weight={button.icon === 'spellcheck' || button.icon === 'listChecks' ? 'bold' : 'fill'} />
              <span className="check-seg__label">{button.label}</span>
              <span className="check-seg__count tnum">{button.count}</span>
            </button>
          )
        })}
      </div>
    </section>
  )
}
