import { useEffect, useMemo, useRef, useState } from 'react'
import { spellCheckApi } from '../../api'
import type { FixMode, SpellFile, SpellFixResult, SpellSession } from '../../api/spellCheck'
import { formatFileSize, formatTime } from '../../lib/format'
import { Button } from '../Button'
import { CheckPreview } from '../check/CheckPreview'
import { FindingsList } from '../check/FindingsList'
import { Menu, type MenuItem } from '../check/Menu'
import {
  buildFindings,
  defaultSelection,
  describeFailure,
  formatRemaining,
  itemMap,
  sameSet,
  toggleItems,
  type FailureText,
  type Finding,
} from '../check/model'
import { FailureNotice, Notice } from '../check/Notice'
import { ConfirmDialog } from '../ConfirmDialog'
import { FileTypeBadge } from '../FileTypeBadge'
import { Icon } from '../Icon'
import { Select } from '../Select'
import { useToast } from '../Toast'
import { IgnoreList } from './IgnoreList'

interface SpellResultViewProps {
  session: SpellSession
  /** Called with the session after the ignore list changed or a fix was made, so the page keeps the latest. */
  onSessionChange: (session: SpellSession) => void
  /** The user wants to check something else; the page deletes the session. */
  onReset: () => void
}

const MINUTE = 60000
const OTHER = 'Cần tự xem lại'
const MODE_OPTIONS = [
  { value: 'track', label: 'Track Changes (ghi dấu)' },
  { value: 'apply', label: 'Sửa trực tiếp' },
]

/** "12 mục" style counts of the kinds of mistake, in the order of the list. */
function kindCounts(findings: Finding[]): [string, number][] {
  const counts = new Map<string, number>()
  for (const finding of findings) counts.set(finding.kindLabel || OTHER, (counts.get(finding.kindLabel || OTHER) ?? 0) + 1)
  return [...counts.entries()].sort((a, b) => (a[0] === OTHER ? 1 : b[0] === OTHER ? -1 : b[1] - a[1]))
}

/** The result of one check: summary and kinds of mistake on top, findings with tick boxes on the left, the text on the right, actions below. */
export function SpellResultView({ session, onSessionChange, onReset }: SpellResultViewProps) {
  const notify = useToast()
  const { result } = session
  const canFix = session.can_fix
  const isText = session.kind === 'text'
  const isPdf = session.kind === 'pdf'

  const findings = useMemo(() => buildFindings(result), [result])
  const items = useMemo(() => itemMap(result.items), [result.items])
  const kinds = useMemo(() => kindCounts(findings), [findings])
  const fixable = useMemo(() => findings.filter((finding) => finding.items.length > 0), [findings])

  const [selected, setSelected] = useState(() => defaultSelection(result.items))
  const [applied, setApplied] = useState<Set<string>>(() => new Set())
  const [failures, setFailures] = useState<Map<string, string>>(() => new Map())
  const [outcome, setOutcome] = useState<SpellFixResult | null>(null)
  const [appliedMode, setAppliedMode] = useState<FixMode | null>(null)
  const [mode, setMode] = useState<FixMode>('track')
  const [kind, setKind] = useState<string>('all')
  const [active, setActive] = useState<{ key: string | null; pi: number | null; nonce: number }>({ key: null, pi: null, nonce: 0 })
  const [reveal, setReveal] = useState<{ key: string; nonce: number } | null>(null)
  const [busy, setBusy] = useState<null | 'fix' | 'ignore' | SpellFile>(null)
  const [error, setError] = useState<FailureText | null>(null)
  const [confirmReset, setConfirmReset] = useState(false)
  const [now, setNow] = useState(() => Date.now())
  const [checkedAt] = useState(session.created_at)

  // The bar sits in the page area, whose width depends on the sidebar: lay it out by its own width, not the window's.
  const barRef = useRef<HTMLDivElement>(null)
  const [barWidth, setBarWidth] = useState(1400)
  useEffect(() => {
    const element = barRef.current
    if (!element) return
    setBarWidth(element.clientWidth)
    const observer = new ResizeObserver(() => setBarWidth(element.clientWidth))
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  const compact = barWidth < 1100

  const statusRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLElement>(null)
  const previewRef = useRef<HTMLElement>(null)

  useEffect(() => {
    if (outcome || error) statusRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [outcome, error])

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), MINUTE)
    return () => window.clearInterval(timer)
  }, [])

  // The list after an ignore: keep only ticks that still have a row.
  useEffect(() => {
    setSelected((current) => new Set([...current].filter((id) => items.has(id))))
  }, [items])

  const visible = useMemo(() => findings.filter((finding) => kind === 'all' || (finding.kindLabel || OTHER) === kind), [findings, kind])
  const chosen = fixable.filter((finding) => finding.items.some((item) => selected.has(item.id))).length
  const unchanged = sameSet(selected, applied) && mode === appliedMode
  const remaining = formatRemaining(session.expires_at, now)
  const expired = remaining === 'đã hết hạn'
  const total = findings.length
  const sure = findings.filter((finding) => finding.confidence === 'cao').length
  const review = findings.filter((finding) => finding.confidence === 'trungbinh').length
  const hints = findings.filter((finding) => finding.confidence === 'thap').length
  const manual = findings.filter((finding) => finding.items.length === 0).length

  const showPreviewIfStacked = () => {
    const element = previewRef.current
    if (element && window.getComputedStyle(element).position !== 'sticky') {
      window.requestAnimationFrame(() => element.scrollIntoView({ block: 'start', behavior: 'smooth' }))
    }
  }

  const locate = (finding: Finding) => {
    setActive((current) => ({ key: finding.key, pi: finding.pis[0] ?? null, nonce: current.nonce + 1 }))
    if (finding.pis.length > 0) showPreviewIfStacked()
  }

  const selectMark = (itemId: string | null, pi: number) => {
    const finding = itemId ? findings.find((candidate) => candidate.key === `item:${itemId}`) : findings.find((candidate) => candidate.items.length === 0 && candidate.pis.includes(pi))
    setActive((current) => ({ key: finding?.key ?? null, pi, nonce: current.nonce + 1 }))
    if (finding) {
      if (kind !== 'all' && (finding.kindLabel || OTHER) !== kind) setKind('all')
      setReveal({ key: finding.key, nonce: Date.now() })
      listRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    }
  }

  const pick = (rows: Finding[]) => setSelected(toggleItems(new Set(), rows.flatMap((finding) => finding.items.map((item) => item.id)), true, items))

  const quickItems: MenuItem[] = [
    { key: 'default', label: 'Mặc định', description: `Chắc chắn và nên xem lại · ${fixable.filter((f) => f.confidence !== 'thap').length} mục`, onSelect: () => setSelected(defaultSelection(result.items)) },
    { key: 'sure', label: 'Chỉ mục chắc chắn', description: `${fixable.filter((f) => f.confidence === 'cao').length} mục`, onSelect: () => pick(fixable.filter((f) => f.confidence === 'cao')) },
    { key: 'all', label: 'Chọn tất cả', description: `${fixable.length} mục`, onSelect: () => pick(fixable) },
    { key: 'visible', label: 'Chỉ nhóm đang xem', description: `${visible.filter((f) => f.items.length > 0).length} mục`, onSelect: () => pick(visible.filter((f) => f.items.length > 0)) },
    { key: 'none', label: 'Bỏ chọn tất cả', icon: 'close', separatorBefore: true, onSelect: () => setSelected(new Set()) },
  ]

  const downloadItems: MenuItem[] = [
    ...(canFix
      ? [{ key: 'fixed', label: 'Tải bản đã sửa', icon: 'download' as const, disabled: busy !== null || !session.fixed, description: session.fixed ? undefined : 'Chọn mục cần sửa rồi bấm “Sửa” để có bản đã sửa', onSelect: () => void download('fixed') }]
      : []),
    { key: 'report', label: 'Tải báo cáo lỗi', icon: 'download' as const, disabled: busy !== null || total === 0, onSelect: () => void download('report') },
  ]

  const changeIgnored = async (words: string[]) => {
    setBusy('ignore')
    setError(null)
    try {
      const next = await spellCheckApi.setIgnored(session.id, words)
      setOutcome(null)
      onSessionChange({ ...next, fixed: session.fixed })
      notify(words.length > session.ignore.length ? 'Đã bỏ qua từ này trong lần soát này.' : 'Đã cập nhật danh sách bỏ qua.', 'success')
    } catch (failure) {
      setError(describeFailure(failure, 'Không cập nhật được danh sách bỏ qua'))
    } finally {
      setBusy(null)
    }
  }

  const runFix = async () => {
    setBusy('fix')
    setError(null)
    try {
      const done = await spellCheckApi.fix(session.id, [...selected], mode)
      setOutcome(done)
      setAppliedMode(mode)
      setApplied(new Set(done.applied))
      setFailures(new Map(done.failed.map((entry) => [entry.id, entry.reason])))
      onSessionChange({ ...session, fixed: true })
      notify(done.applied.length > 0 ? `Đã sửa ${done.applied.length} chỗ.` : 'Không có mục nào áp dụng được.', done.applied.length > 0 ? 'success' : 'error')
    } catch (failure) {
      setError(describeFailure(failure, 'Không sửa được'))
    } finally {
      setBusy(null)
    }
  }

  const download = async (file: SpellFile) => {
    setBusy(file)
    try {
      spellCheckApi.saveBlob(await spellCheckApi.fetchFile(session.id, file), spellCheckApi.downloadName(session, file))
    } catch (failure) {
      const text = describeFailure(failure, 'Không tải được tệp')
      notify(`${text.title}: ${text.message}`, 'error')
    } finally {
      setBusy(null)
    }
  }

  const copyText = async () => {
    if (!outcome?.text) return
    try {
      await navigator.clipboard.writeText(outcome.text)
      notify('Đã chép văn bản đã sửa.', 'success')
    } catch {
      notify('Không chép được. Hãy tải văn bản đã sửa về.', 'error')
    }
  }

  const requestReset = () => (session.fixed || session.ignore.length > 0 ? setConfirmReset(true) : onReset())
  const backToList = () => listRef.current?.scrollIntoView({ block: 'start', behavior: 'smooth' })

  const headline = total === 0 ? 'Không thấy lỗi chính tả' : `${total} chỗ nghi sai chính tả`
  const sub = total === 0
    ? 'Chương trình không thấy lỗi nào, nhưng vẫn nên đọc lại những chỗ quan trọng.'
    : [sure && `${sure} chắc chắn`, review && `${review} nên xem lại`, hints && `${hints} gợi ý`, manual && `${manual} cần tự xem lại`].filter(Boolean).join(' · ')
  const meta = [
    session.kind === 'text' && session.name === 'van_ban.txt' ? 'Văn bản dán' : result.kind_label,
    `${result.chars.toLocaleString('vi-VN')} ký tự`,
    session.name === 'van_ban.txt' ? null : formatFileSize(session.size),
    `Soát lúc ${formatTime(checkedAt)}`,
  ].filter(Boolean).join(' · ')
  const title = session.name === 'van_ban.txt' ? 'Văn bản đã dán' : session.name

  return (
    <div className="check check--result spell">
      <header className="check-head check-head--row">
        <h1 className="check-head__title">Kiểm tra chính tả</h1>
        <p className="check-temp" title="Chỉ có bạn xem được, không lập chỉ mục, không vào kho văn bản; tự xóa khi bạn rời màn này hoặc hết hạn.">
          <Icon name="shield" size={18} />
          <span>Bản tạm, chỉ bạn xem được{remaining && <> · {remaining}</>}</span>
        </p>
      </header>

      <section className="check-verdict" aria-label="Kết quả soát chính tả">
        <div className="check-verdict__file">
          <FileTypeBadge name={session.name} size="md" />
          <div className="check-verdict__id">
            <div className="check-verdict__name" title={title}>{title}</div>
            <div className="check-verdict__meta" title={meta}>{meta}</div>
          </div>
          <Button icon="spellcheck" onClick={requestReset} disabled={busy !== null}>Soát văn bản khác</Button>
        </div>
        <div className={`check-verdict__main check-verdict__main--${total === 0 ? 'pass' : 'fail'}`}>
          <span className="check-verdict__mark"><Icon name={total === 0 ? 'checkCircle' : 'spellcheck'} size={28} weight={total === 0 ? 'fill' : 'bold'} /></span>
          <div>
            <h2 className="check-verdict__headline spell-headline">{headline}</h2>
            {sub && <p className="check-verdict__sub">{sub}{result.ignored > 0 ? ` · đã bỏ qua ${result.ignored}` : ''}</p>}
          </div>
        </div>
        {kinds.length > 0 && (
          <div className="check-seg" role="group" aria-label="Lọc theo loại lỗi">
            <KindButton label="Tất cả" count={total} on={kind === 'all'} onClick={() => { setKind('all'); setReveal(null) }} />
            {kinds.map(([label, count]) => (
              <KindButton key={label} label={label} count={count} on={kind === label} onClick={() => { setKind(kind === label ? 'all' : label); setReveal(null) }} />
            ))}
          </div>
        )}
        <IgnoreList words={session.ignore} busy={busy === 'ignore'} disabled={busy !== null || expired} onChange={changeIgnored} />
      </section>

      <div className="check-split">
        <section className="check-left" aria-label="Các lỗi chính tả" ref={listRef}>
          <div className="check-status" ref={statusRef}>
            {isPdf && (
              <Notice tone="info" icon="info" title="PDF chỉ được liệt kê lỗi">
                <p>{result.note || 'PDF không sửa trực tiếp được: sửa ở tệp gốc rồi xuất lại PDF.'} Tải báo cáo để có danh sách lỗi.</p>
              </Notice>
            )}
            {expired && (
              <Notice tone="warning" icon="clock" title="Bản tạm đã hết hạn">
                <p>Máy chủ có thể đã xóa tệp này. Hãy soát lại nếu thao tác báo lỗi.</p>
              </Notice>
            )}
            {error && <FailureNotice failure={error} actions={error.kind === 'gone' ? <Button icon="spellcheck" onClick={onReset}>Soát lại</Button> : undefined} />}
            {outcome && <Outcome outcome={outcome} before={session.counts.spelling} isText={isText} busy={busy !== null} onDownload={download} onCopy={copyText} />}
          </div>

          <div className="check-listcard">
            {total > 0 && (
              <div className="check-toolbar">
                <h2 className="check-toolbar__title">
                  Từ nghi sai
                  <span className="check-toolbar__count tnum">{visible.length}{visible.length !== total ? `/${total}` : ''}</span>
                </h2>
                {canFix && fixable.length > 0 && (
                  <>
                    <span className="check-toolbar__sel tnum" aria-live="polite">Đã chọn {chosen}/{fixable.length} mục tự sửa</span>
                    <Menu label="Chọn nhanh" ariaLabel="Chọn nhanh mục tự sửa được" icon="listChecks" items={quickItems} align="end" disabled={busy !== null} />
                  </>
                )}
              </div>
            )}
            <div className="check-panel">
              {total === 0 ? (
                <div className="check-empty">
                  <span className="check-empty__icon"><Icon name="checkCircle" size={24} weight="fill" /></span>
                  <p className="check-empty__title">Không thấy lỗi chính tả</p>
                  <p className="check-empty__text">
                    {result.ignored > 0 ? `${result.ignored} chỗ đã được bạn bỏ qua trong lần soát này.` : 'Chương trình không phát hiện từ nào nghi sai.'}
                  </p>
                </div>
              ) : (
                <FindingsList
                  key={`${session.id}-${checkedAt}-${kind}-${session.ignore.length}`}
                  findings={visible}
                  tiers={result.tiers}
                  selected={selected}
                  applied={applied}
                  failures={failures}
                  canFix={canFix}
                  activeKey={active.key}
                  reveal={reveal}
                  onToggle={(ids, on) => setSelected((current) => toggleItems(current, ids, on, items))}
                  onLocate={locate}
                  onIgnore={(finding) => void changeIgnored([...session.ignore, finding.current])}
                  emptyText="Không có mục nào trong nhóm này"
                />
              )}
            </div>
          </div>
        </section>

        <aside className="check-pv" aria-label="Xem trước văn bản" ref={previewRef}>
          <button type="button" className="btn check-pv__back" onClick={backToList}>
            <Icon name="arrowLeft" size={16} />
            Về danh sách lỗi
          </button>
          <CheckPreview
            paras={result.paras}
            levels={new Map()}
            items={items}
            activePi={active.pi}
            activeNonce={active.nonce}
            estimatedPages={!isPdf}
            onSelectPara={() => undefined}
            onSelectMark={selectMark}
            activeMark={active.key?.startsWith('item:') ? active.key.slice(5) : null}
            legend="spelling"
            footNote={
              session.fixed
                ? 'Xem trước là bản gốc; các thay đổi nằm trong bản đã sửa.'
                : isText ? 'Xem trước là văn bản bạn đưa vào.' : 'Xem trước dựng từ nội dung tệp gốc; ngắt trang chỉ là ước tính.'
            }
          />
        </aside>
      </div>

      <div className="check-bar" ref={barRef} role="region" aria-label="Thao tác với kết quả">
        <div className="check-bar__inner">
          {canFix && (
            <div className="check-bar__fix">
              {!isText && <Select aria-label="Cách sửa" value={mode} options={MODE_OPTIONS} onChange={(value) => setMode(value as FixMode)} disabled={busy !== null} className="check-bar__mode" />}
              <Button variant="primary" icon="check" className="check-bar__primary" loading={busy === 'fix'} disabled={busy !== null || chosen === 0 || unchanged || expired} onClick={runFix}>
                {`Sửa ${chosen} mục đã chọn`}
              </Button>
            </div>
          )}
          {compact ? (
            <Menu label="Tải về" ariaLabel="Tải về" icon="download" items={downloadItems} direction="up" align="end" className="check-bar__dl" />
          ) : (
            <div className="check-bar__downloads" role="group" aria-label="Tải về">
              <span className="check-bar__caption">Tải về</span>
              {canFix && (
                <Button icon="download" loading={busy === 'fixed'} disabled={busy !== null || !session.fixed} title={session.fixed ? undefined : 'Chọn mục cần sửa rồi bấm “Sửa” để có bản đã sửa'} onClick={() => void download('fixed')}>
                  Bản đã sửa
                </Button>
              )}
              <Button icon="download" loading={busy === 'report'} disabled={busy !== null || total === 0} onClick={() => void download('report')}>Báo cáo lỗi</Button>
            </div>
          )}
          <span className="spacer" />
          <Button variant="ghost" onClick={requestReset} disabled={busy !== null}>Soát văn bản khác</Button>
        </div>
      </div>

      {confirmReset && (
        <ConfirmDialog
          title="Soát văn bản khác?"
          confirmLabel="Bỏ kết quả và soát văn bản khác"
          danger
          onConfirm={() => { setConfirmReset(false); onReset() }}
          onCancel={() => setConfirmReset(false)}
        >
          Kết quả{session.fixed ? ' và bản đã sửa' : ''} của “{title}” sẽ bị xóa khỏi máy chủ. Hãy tải bản đã sửa về trước nếu bạn còn cần.
        </ConfirmDialog>
      )}
    </div>
  )
}

function KindButton({ label, count, on, onClick }: { label: string; count: number; on: boolean; onClick: () => void }) {
  return (
    <button type="button" className={`check-seg__btn check-seg__btn--${label === 'Tất cả' ? 'primary' : 'info'}${on ? ' is-on' : ''}`} aria-pressed={on} onClick={onClick}>
      <span className="check-seg__label">{label}</span>
      <span className="check-seg__count tnum">{count}</span>
    </button>
  )
}

interface OutcomeProps {
  outcome: SpellFixResult
  /** Findings in the original (after the ignore list). */
  before: number
  isText: boolean
  busy: boolean
  onDownload: (file: SpellFile) => void
  onCopy: () => void
}

/** What the last "Sửa" did: how many places changed, what a new check still finds, the download or copy buttons. */
function Outcome({ outcome, before, isText, busy, onDownload, onCopy }: OutcomeProps) {
  const applied = outcome.applied.length
  return (
    <div className="check-outcome">
      <Notice
        tone={applied > 0 ? 'success' : 'warning'}
        icon={applied > 0 ? 'checkCircle' : 'alert'}
        title={applied > 0 ? `Đã sửa ${applied} chỗ` : 'Không có mục nào áp dụng được'}
        actions={
          applied > 0 ? (
            <>
              <Button icon="download" variant="primary" disabled={busy} onClick={() => onDownload('fixed')}>Tải bản đã sửa</Button>
              {isText && <Button icon="copy" disabled={busy || !outcome.text} onClick={onCopy}>Chép văn bản đã sửa</Button>}
            </>
          ) : undefined
        }
      >
        <p>Bản đã sửa còn {outcome.after.spelling} chỗ nghi sai chính tả (bản gốc: {before}).</p>
        {!isText && <p>Mỗi chỗ sửa nằm trong Track Changes của Word (nếu bạn chọn ghi dấu): mở bằng Word, vào Review để Chấp nhận hoặc Từ chối.</p>}
      </Notice>
      {outcome.failed.length > 0 && (
        <Notice tone="warning" icon="alert" title={`${outcome.failed.length} mục không áp dụng được`}>
          <ul className="check-failed">
            {outcome.failed.map((entry) => <li key={entry.id}>{entry.reason}</li>)}
          </ul>
        </Notice>
      )}
    </div>
  )
}
