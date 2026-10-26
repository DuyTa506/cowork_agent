import { useEffect, useMemo, useRef, useState } from 'react'
import { formatCheckApi } from '../../api'
import type { CheckFile, CheckSession, FixMode, FixResult } from '../../api/formatCheck'
import { useAsyncData } from '../../hooks/useAsyncData'
import { Button } from '../Button'
import { ConfirmDialog } from '../ConfirmDialog'
import { Icon } from '../Icon'
import { useToast } from '../Toast'
import { ActionBar } from './ActionBar'
import { CheckPreview } from './CheckPreview'
import { FindingsList } from './FindingsList'
import { FixOutcome } from './FixOutcome'
import { Menu } from './Menu'
import { Notice, FailureNotice } from './Notice'
import { SaveToStoreDialog } from './SaveToStoreDialog'
import { VerdictBar, type LevelFilter } from './VerdictBar'
import {
  buildFindings,
  countByLevel,
  defaultSelection,
  describeFailure,
  formatRemaining,
  itemMap,
  paragraphLevels,
  pickMatches,
  quickSelection,
  sameSet,
  toggleItems,
  type FailureText,
  type Finding,
  type QuickPick,
} from './model'

interface CheckResultViewProps {
  session: CheckSession
  /** Called with the session after a recheck or fix so the page keeps the latest. */
  onSessionChange: (session: CheckSession) => void
  /** The user wants another file; the page deletes the session. */
  onReset: () => void
}

const MINUTE = 60000

/** Result of one checked file: verdict on top, findings with selectable fixes on the left, document preview on the right, actions at the bottom. */
export function CheckResultView({ session, onSessionChange, onReset }: CheckResultViewProps) {
  const notify = useToast()
  const { result } = session
  const canFix = session.can_fix && result.can_fix

  const findings = useMemo(() => buildFindings(result), [result])
  const items = useMemo(() => itemMap(result.items), [result.items])
  const levels = useMemo(() => paragraphLevels(findings), [findings])
  const counts = useMemo(() => countByLevel(findings), [findings])
  const fixable = useMemo(() => findings.filter((finding) => finding.items.length > 0), [findings])

  const [selected, setSelected] = useState(() => defaultSelection(result.items))
  const [applied, setApplied] = useState<Set<string>>(() => new Set())
  const [failures, setFailures] = useState<Map<string, string>>(() => new Map())
  const [outcome, setOutcome] = useState<FixResult | null>(null)
  /** Mode of the corrected copy that exists, so changing only the mode allows fixing again. */
  const [appliedMode, setAppliedMode] = useState<FixMode | null>(null)
  const [mode, setMode] = useState<FixMode>('track')
  const [filter, setFilter] = useState<LevelFilter>('all')
  const [active, setActive] = useState<{ key: string | null; pi: number | null; nonce: number }>({ key: null, pi: null, nonce: 0 })
  const [reveal, setReveal] = useState<{ key: string; nonce: number } | null>(null)
  const [busy, setBusy] = useState<null | 'fix' | 'recheck' | CheckFile>(null)
  const [error, setError] = useState<FailureText | null>(null)
  const [saveOpen, setSaveOpen] = useState(false)
  const [confirmReset, setConfirmReset] = useState(false)
  const [profile, setProfile] = useState(session.profile)
  const [spell, setSpell] = useState(session.spell)
  const [checkedAt, setCheckedAt] = useState(session.created_at)
  const [now, setNow] = useState(() => Date.now())

  const statusRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLElement>(null)
  const previewRef = useRef<HTMLElement>(null)
  const { data: options } = useAsyncData((signal) => formatCheckApi.getOptions(signal), [])

  // The result of a fix or an error is above the list: bring it into view, the list may have been scrolled far down.
  useEffect(() => {
    if (outcome || error) statusRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [outcome, error])

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), MINUTE)
    return () => window.clearInterval(timer)
  }, [])

  const profileOptions = useMemo(() => {
    const list = (options?.profiles ?? []).map((item) => ({ value: item.id, label: item.experimental ? `${item.label} (thử nghiệm)` : item.label }))
    return list.some((entry) => entry.value === session.profile) ? list : [{ value: session.profile, label: result.profile.label }, ...list]
  }, [options, session.profile, result.profile.label])

  const visible = useMemo(() => findings.filter((finding) => filter === 'all' || finding.level === filter), [findings, filter])

  const chosen = fixable.filter((finding) => finding.items.some((item) => selected.has(item.id) && !item.locked)).length
  const unchanged = sameSet(selected, applied) && mode === appliedMode
  const optionsChanged = profile !== session.profile || spell !== session.spell
  const remaining = formatRemaining(session.expires_at, now)
  const expired = remaining === 'đã hết hạn'
  const isPdf = session.kind === 'pdf'
  const pageCount = result.paras.reduce((most, para) => Math.max(most, para.page ?? para.pg ?? 0), 0)
  const noFindings = findings.length === 0 && session.counts.format + session.counts.spelling === 0

  /** Below 900 px the preview sits under the list: bring it into view after asking for a location. */
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

  const selectPara = (pi: number) => {
    const finding = findings.find((candidate) => candidate.pis.includes(pi))
    setActive((current) => ({ key: finding?.key ?? null, pi, nonce: current.nonce + 1 }))
    if (finding) {
      // A finding hidden by the filter would never show: widen the filter first.
      if (filter !== 'all' && finding.level !== filter) setFilter('all')
      setReveal({ key: finding.key, nonce: Date.now() })
    }
  }

  const quick = (value: QuickPick) => setSelected(quickSelection(value, findings, items))

  const quickItems = [
    { key: 'all', label: 'Chọn tất cả', pick: 'all' as const },
    { key: 'default', label: 'Mặc định', description: 'Độ tin cậy cao và trung bình', pick: 'default' as const },
    { key: 'error', label: 'Chỉ mức bắt buộc', pick: 'error' as const },
    { key: 'warning', label: 'Chỉ mức cảnh báo', pick: 'warning' as const },
    { key: 'spelling', label: 'Chỉ chính tả', pick: 'spelling' as const },
    { key: 'none', label: 'Bỏ chọn tất cả', pick: 'none' as const },
  ].map((entry, index) => {
    const count = pickMatches(entry.pick, findings).length
    return {
      key: entry.key,
      label: entry.label,
      description: entry.pick === 'none' ? undefined : `${entry.description ? `${entry.description} · ` : ''}${count} mục`,
      icon: entry.pick === 'none' ? ('close' as const) : undefined,
      separatorBefore: index === 5,
      onSelect: () => quick(entry.pick),
    }
  })

  const runFix = async () => {
    setBusy('fix')
    setError(null)
    try {
      const done = await formatCheckApi.fix(session.id, [...selected], mode)
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

  const runRecheck = async () => {
    setBusy('recheck')
    setError(null)
    try {
      const next = await formatCheckApi.recheck(session.id, { profile, spell })
      setSelected(defaultSelection(next.result.items))
      setApplied(new Set())
      setFailures(new Map())
      setOutcome(null)
      setAppliedMode(null)
      setFilter('all')
      setActive({ key: null, pi: null, nonce: 0 })
      setCheckedAt(new Date().toISOString())
      onSessionChange(next)
    } catch (failure) {
      setError(describeFailure(failure, 'Không kiểm tra lại được'))
    } finally {
      setBusy(null)
    }
  }

  const download = async (file: CheckFile) => {
    setBusy(file)
    try {
      formatCheckApi.saveBlob(await formatCheckApi.fetchFile(session.id, file), formatCheckApi.downloadName(session, file))
    } catch (failure) {
      const text = describeFailure(failure, 'Không tải được tệp')
      notify(`${text.title}: ${text.message}`, 'error')
    } finally {
      setBusy(null)
    }
  }

  const requestReset = () => (session.fixed ? setConfirmReset(true) : onReset())
  const backToList = () => listRef.current?.scrollIntoView({ block: 'start', behavior: 'smooth' })

  return (
    <div className="check check--result">
      <header className="check-head check-head--row">
        <h1 className="check-head__title">Kiểm tra thể thức và chính tả</h1>
        <p className="check-temp" title="Tệp chỉ có bạn xem được, không lập chỉ mục, không vào kho văn bản; tự xóa khi bạn rời màn này hoặc hết hạn.">
          <Icon name="shield" size={18} />
          <span>Tệp tạm, chỉ bạn xem được{remaining && <> · {remaining}</>}</span>
        </p>
      </header>

      <VerdictBar
        session={session}
        counts={counts}
        fixable={fixable.length}
        pageCount={pageCount}
        checkedAt={checkedAt}
        filter={filter}
        onFilter={(next) => { setFilter(next); setReveal(null) }}
        profile={profile}
        profileOptions={profileOptions}
        onProfile={setProfile}
        spell={spell}
        onSpell={setSpell}
        optionsChanged={optionsChanged}
        rechecking={busy === 'recheck'}
        disabled={busy !== null || expired}
        onRecheck={runRecheck}
      />

      <div className="check-split">
        <section className="check-left" aria-label="Kết quả kiểm tra" ref={listRef}>
          <div className="check-status" ref={statusRef}>
            {isPdf && (
              <Notice tone="info" icon="info" title="PDF chỉ được kiểm tra">
                <p>{result.note || 'PDF không sửa trực tiếp được: sửa ở tệp gốc rồi xuất lại PDF.'}</p>
              </Notice>
            )}
            {expired && (
              <Notice tone="warning" icon="clock" title="Tệp tạm đã hết hạn">
                <p>Máy chủ có thể đã xóa tệp này. Hãy chọn tệp lại nếu thao tác báo lỗi.</p>
              </Notice>
            )}
            {error && (
              <FailureNotice
                failure={error}
                actions={error.kind === 'gone' ? <Button icon="upload" onClick={onReset}>Chọn tệp khác</Button> : undefined}
              />
            )}
            {outcome && <FixOutcome outcome={outcome} before={session.counts} items={items} busy={busy !== null} onDownload={download} />}
          </div>

          <div className="check-listcard">
          {!noFindings && (
            <div className="check-toolbar">
              <h2 className="check-toolbar__title">
                Phát hiện
                <span className="check-toolbar__count tnum">{visible.length}{visible.length !== findings.length ? `/${findings.length}` : ''}</span>
              </h2>
              {canFix && fixable.length > 0 && (
                <>
                  <span className="check-toolbar__sel tnum" aria-live="polite">Đã chọn {chosen}/{fixable.length} mục tự sửa</span>
                  <Menu
                    label="Chọn nhanh"
                    ariaLabel="Chọn nhanh mục tự sửa được"
                    icon="listChecks"
                    items={quickItems}
                    align="end"
                    disabled={busy !== null}
                  />
                </>
              )}
            </div>
          )}

          <div className="check-panel">
            {noFindings ? (
              <div className="check-empty">
                <span className="check-empty__icon"><Icon name="checkCircle" size={24} weight="fill" /></span>
                <p className="check-empty__title">Không phát hiện lỗi</p>
                <p className="check-empty__text">Văn bản đúng thể thức theo bộ luật đã chọn{session.spell ? ' và không có lỗi chính tả' : ''}.</p>
              </div>
            ) : (
              <FindingsList
                key={`${session.id}-${checkedAt}-${filter}`}
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
                emptyText="Không có mục nào trong nhóm này"
              />
            )}
          </div>
          </div>
        </section>

        <aside className="check-pv" aria-label="Xem trước văn bản" ref={previewRef}>
          <button type="button" className="btn check-pv__back" onClick={backToList}>
            <Icon name="arrowLeft" size={16} />
            Về danh sách phát hiện
          </button>
          <CheckPreview
            paras={result.paras}
            levels={levels}
            items={items}
            activePi={active.pi}
            activeNonce={active.nonce}
            estimatedPages={!isPdf}
            onSelectPara={selectPara}
            busy={busy === 'recheck'}
            footNote={
              session.fixed
                ? 'Xem trước là tệp gốc; các thay đổi nằm trong bản đã sửa (tải về để xem).'
                : 'Xem trước dựng từ nội dung tệp gốc; ngắt trang chỉ là ước tính.'
            }
          />
        </aside>
      </div>

      <ActionBar
        canFix={canFix}
        fixed={session.fixed}
        busy={busy}
        chosen={chosen}
        unchanged={unchanged}
        expired={expired}
        mode={mode}
        onMode={setMode}
        onFix={runFix}
        onDownload={download}
        onSave={() => setSaveOpen(true)}
        onReset={requestReset}
      />

      {saveOpen && <SaveToStoreDialog checkId={session.id} fileName={session.name} hasFixed={session.fixed} onClose={() => setSaveOpen(false)} />}
      {confirmReset && (
        <ConfirmDialog
          title="Chọn tệp khác?"
          confirmLabel="Bỏ kết quả và chọn tệp khác"
          danger
          onConfirm={() => { setConfirmReset(false); onReset() }}
          onCancel={() => setConfirmReset(false)}
        >
          Bản đã sửa của “{session.name}” sẽ bị xóa khỏi máy chủ. Hãy tải bản đã sửa hoặc lưu vào kho trước nếu bạn còn cần.
        </ConfirmDialog>
      )}
    </div>
  )
}
