import { useEffect, useMemo, useRef, useState } from 'react'
import type { Tier } from '../../api/formatCheck'
import { Button } from '../Button'
import { Chip } from '../Chip'
import { Icon } from '../Icon'
import { LEVELS, LEVEL_ORDER, type Finding, type Level } from './model'

const PAGE = 150

interface FindingsListProps {
  findings: Finding[]
  tiers: Record<Tier, string>
  selected: Set<string>
  /** Items that are in the corrected copy. */
  applied: Set<string>
  /** Why an item could not be applied, by item id. */
  failures: Map<string, string>
  canFix: boolean
  activeKey: string | null
  /** Set when the preview asked for a finding: the list scrolls to it. */
  reveal: { key: string; nonce: number } | null
  onToggle: (ids: string[], on: boolean) => void
  onLocate: (finding: Finding) => void
  /** Spelling screen: skip the word of a row everywhere in this session. */
  onIgnore?: (finding: Finding) => void
  /** Shown when there is nothing to list; tells "no findings at all" from "none in this filter". */
  emptyText: string
}

/** Findings grouped by severity; fixable ones have a checkbox. Long lists are shown in steps of 150 rows. */
export function FindingsList({ findings, tiers, selected, applied, failures, canFix, activeKey, reveal, onToggle, onLocate, onIgnore, emptyText }: FindingsListProps) {
  const [limit, setLimit] = useState(PAGE)

  useEffect(() => {
    if (!reveal) return
    const index = findings.findIndex((finding) => finding.key === reveal.key)
    if (index >= limit) setLimit(index + PAGE)
    // Wait for the extra rows to render before scrolling.
    const frame = window.requestAnimationFrame(() => document.getElementById(rowId(reveal.key))?.scrollIntoView({ block: 'center', behavior: 'smooth' }))
    return () => window.cancelAnimationFrame(frame)
    // Only a new request from the preview should scroll the list.
  }, [reveal])

  const shown = useMemo(() => findings.slice(0, limit), [findings, limit])
  const groups = LEVEL_ORDER.map((level) => ({ level, rows: shown.filter((finding) => finding.level === level) })).filter((group) => group.rows.length > 0)

  if (findings.length === 0) {
    return (
      <div className="check-empty">
        <span className="check-empty__icon"><Icon name="checkCircle" size={24} weight="fill" /></span>
        <p className="check-empty__title">{emptyText}</p>
      </div>
    )
  }

  return (
    <div className="check-list">
      {groups.map(({ level, rows }) => {
        const all = findings.filter((finding) => finding.level === level)
        const fixable = all.filter((finding) => finding.items.length > 0).length
        return (
          <section key={level} aria-labelledby={`check-group-${level}`}>
            <h3 className="check-group" id={`check-group-${level}`}>
              <span className={`check-group__icon check-tone--${LEVELS[level].tone}`}><Icon name={LEVELS[level].icon} size={16} weight="fill" /></span>
              {LEVELS[level].plural}
              <span className="check-group__count tnum">{all.length}</span>
              {canFix && fixable > 0 && <span className="check-group__fix tnum">{fixable} tự sửa được</span>}
            </h3>
            <ul>
              {rows.map((finding) => (
                <FindingRow
                  key={finding.key}
                  finding={finding}
                  level={level}
                  tiers={tiers}
                  canFix={canFix}
                  selected={selected}
                  applied={applied}
                  failures={failures}
                  active={activeKey === finding.key}
                  onToggle={onToggle}
                  onLocate={onLocate}
                  onIgnore={onIgnore}
                />
              ))}
            </ul>
          </section>
        )
      })}
      {findings.length > limit && (
        <div className="check-more">
          <Button onClick={() => setLimit((value) => value + PAGE)}>
            Hiện thêm {Math.min(PAGE, findings.length - limit)} mục (còn {findings.length - limit})
          </Button>
        </div>
      )}
    </div>
  )
}

const rowId = (key: string) => `check-find-${key}`

interface RowProps {
  finding: Finding
  level: Level
  tiers: Record<Tier, string>
  canFix: boolean
  selected: Set<string>
  applied: Set<string>
  failures: Map<string, string>
  active: boolean
  onToggle: (ids: string[], on: boolean) => void
  onLocate: (finding: Finding) => void
  onIgnore?: (finding: Finding) => void
}

function FindingRow({ finding, level, tiers, canFix, selected, applied, failures, active, onToggle, onLocate, onIgnore }: RowProps) {
  const { items } = finding
  const item = items[0]
  const boxRef = useRef<HTMLInputElement>(null)
  const [open, setOpen] = useState(false)
  const locatable = finding.pis.length > 0
  const ticked = items.filter((entry) => selected.has(entry.id)).length
  const checked = items.length > 0 && ticked === items.length
  const locked = items.length > 0 && items.every((entry) => entry.locked)
  const needsOther = Boolean(item?.requires) && !locked
  const done = items.length > 0 && items.every((entry) => applied.has(entry.id))
  const failure = items.map((entry) => failures.get(entry.id)).find((reason) => reason !== undefined)
  const classes = ['check-row', `check-row--${LEVELS[level].tone}`, active && 'check-row--active', open && 'check-row--open'].filter(Boolean).join(' ')

  // Some of the places of a row ticked (after a quick pick, or because they are required by another row).
  useEffect(() => {
    if (boxRef.current) boxRef.current.indeterminate = ticked > 0 && ticked < items.length
  }, [ticked, items.length])

  // Asking for this finding (from the preview or by clicking it) opens its details.
  useEffect(() => {
    if (active) setOpen(true)
  }, [active])

  const spelling = Boolean(finding.context)
  const hasMore = Boolean(finding.current || finding.target || finding.basis || finding.reason || finding.where || item)
  const click = () => {
    if (locatable) onLocate(finding)
    else setOpen((value) => !value)
  }

  return (
    <li id={rowId(finding.key)} className={classes}>
      {canFix && (
        item ? (
          <label className="check-tick">
            <input
              ref={boxRef}
              type="checkbox"
              checked={checked}
              disabled={locked}
              aria-label={`Chọn sửa: ${finding.message}`}
              onChange={(event) => onToggle(items.map((entry) => entry.id), event.target.checked)}
            />
          </label>
        ) : (
          <span className="check-tick check-tick--none" aria-hidden="true" />
        )
      )}
      <div className="check-row__body">
        <div className="check-row__head">
          <button type="button" className="check-row__main" onClick={click} title={locatable ? 'Xem vị trí trong văn bản' : undefined}>
            <span className={`check-row__icon check-tone--${LEVELS[level].tone}`}>
              <Icon name={LEVELS[level].icon} size={18} weight={level === 'spelling' ? 'bold' : 'fill'} />
            </span>
            <span className="check-row__text">
              <span className="check-row__title">{finding.message}</span>
              <span className="check-row__detail">
                {spelling && finding.context ? (
                  <>…{finding.context.before}<mark className="check-ctx">{finding.context.found}</mark>{finding.context.after}…</>
                ) : (
                  finding.hint || finding.where
                )}
                {spelling && finding.hint && <span className="check-row__suggest"> · {finding.hint}</span>}
              </span>
            </span>
          </button>
          <span className="check-row__tags">
            {canFix && (item ? <Chip tone="blue" icon="tools">Tự sửa</Chip> : <Chip tone="grey" icon="edit">Sửa tay</Chip>)}
            {locked && <Chip tone="grey" icon="lock">Luôn áp dụng</Chip>}
            {done && <Chip tone="green" icon="checkCircle">Đã sửa</Chip>}
            {failure !== undefined && <Chip tone="red" icon="alertCircle">Không áp dụng được</Chip>}
            {onIgnore && finding.current && !/[␣⍽⇥]/.test(finding.current) && (
              <button type="button" className="check-row__ignore" title={`Bỏ qua “${finding.current}” trong cả văn bản`} aria-label={`Bỏ qua từ “${finding.current}”`} onClick={() => onIgnore(finding)}>
                <Icon name="eyeOff" size={16} />
                <span>Bỏ qua</span>
              </button>
            )}
          </span>
          {hasMore && (
            <button
              type="button"
              className="check-row__toggle"
              aria-expanded={open}
              aria-label={open ? 'Thu gọn chi tiết' : 'Xem chi tiết'}
              title={open ? 'Thu gọn chi tiết' : 'Xem chi tiết'}
              onClick={() => setOpen((value) => !value)}
            >
              <Icon name={open ? 'chevronUp' : 'chevronDown'} size={16} />
            </button>
          )}
        </div>

        {failure !== undefined && <p className="check-row__fail"><Icon name="alertCircle" size={16} weight="fill" />Không áp dụng được: {failure}</p>}

        {open && (
          <div className="check-more-info">
            {(finding.current || finding.target) && (
              <div className="check-diff">
                <div className="check-diff__cell">
                  <span className="check-diff__label">Hiện có</span>
                  <span className="check-diff__value">{finding.current || 'Không có'}</span>
                </div>
                <Icon name="arrowRight" size={16} className="check-diff__arrow" />
                <div className="check-diff__cell check-diff__cell--to">
                  <span className="check-diff__label">{item ? 'Cần sửa' : 'Gợi ý'}</span>
                  <span className="check-diff__value">{finding.target || (spelling ? 'Xóa từ này' : 'Bổ sung hoặc sửa tay')}</span>
                </div>
              </div>
            )}
            <dl className="check-facts">
              {finding.where && (
                <>
                  <dt>Vị trí</dt>
                  <dd>{finding.where}</dd>
                </>
              )}
              {finding.reason && (
                <>
                  <dt>{!item ? 'Vì sao cần sửa tay' : 'Nhận xét'}</dt>
                  <dd>{finding.reason}</dd>
                </>
              )}
              {finding.basis && (
                <>
                  <dt>Căn cứ</dt>
                  <dd>{finding.basis}</dd>
                </>
              )}
              {canFix && item && finding.confidence && (
                <>
                  <dt>Độ tin cậy</dt>
                  <dd>{tiers[finding.confidence] ?? finding.confidence}</dd>
                </>
              )}
              {canFix && item && (locked || needsOther) && (
                <>
                  <dt>Ghi chú</dt>
                  <dd>{locked ? 'Luôn được áp dụng cùng bản sửa, không bỏ chọn được.' : 'Đi kèm một mục khác: chọn mục này sẽ chọn cả mục kia.'}</dd>
                </>
              )}
            </dl>
          </div>
        )}
      </div>
    </li>
  )
}
