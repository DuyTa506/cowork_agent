import { useEffect, useState } from 'react'
import type { ChatStep, StepDocumentRef } from '../../api/chat'
import { Icon, type IconName } from '../Icon'
import { formatSeconds, runningLabel, stepDuration } from './log'

interface TraceLogProps {
  steps: ChatStep[]
  /** The turn is still going. */
  running: boolean
  /** Start of the running turn (ms since epoch), for the timer. */
  startedAt?: number
  /** Total time of a finished turn. */
  durationMs: number
  /** Why the turn ended early. */
  outcome: 'done' | 'error' | 'stopped' | 'running'
  onOpenDocument: (reference: StepDocumentRef) => void
}

const TOOL_ICONS: Record<string, IconName> = {
  search_documents: 'search',
  list_documents: 'folder',
  read_document: 'file',
  summarize_document: 'clipboard',
  search_attachments: 'clip',
  list_attachments: 'clip',
  read_attachment: 'clip',
  canvas_create: 'canvas',
  canvas_set_fields: 'canvas',
  canvas_set_content: 'canvas',
  canvas_edit_block: 'canvas',
  canvas_edit_table: 'canvas',
  canvas_read: 'canvas',
  canvas_check: 'shield',
}

const iconOf = (step: ChatStep): IconName => (step.kind === 'thinking' ? 'lightbulb' : (TOOL_ICONS[step.tool ?? ''] ?? 'tools'))

/** The server appends " · 0,1 giây" to a summary: the duration has its own column. */
const cleanSummary = (summary: string): string =>
  summary.replace(/\s+/g, ' ').replace(/\s*·\s*\d+(?:,\d+)?\s*giây$/, '').replace(/^[\s·]+/, '').trim()

const hasBody = (step: ChatStep): boolean => {
  const detail = step.detail
  if (!detail) return false
  return Boolean(detail.text || detail.result?.error || detail.result?.documents?.length || (detail.arguments && Object.keys(detail.arguments).length))
}

const argumentText = (value: unknown): string => (typeof value === 'string' ? value : JSON.stringify(value))

function StepCard({ step, onOpenDocument }: { step: ChatStep; onOpenDocument: TraceLogProps['onOpenDocument'] }) {
  const [open, setOpen] = useState(false)
  const expandable = hasBody(step)
  const summary = cleanSummary(step.summary)
  const duration = step.kind === 'thinking' ? '' : stepDuration(step)
  const detail = step.detail
  const content = (
    <>
      <span className="tstep__icon">
        {step.status === 'running' ? <Icon name="spinner" size={18} className="spin" /> : <Icon name={step.status === 'error' ? 'alertCircle' : iconOf(step)} size={18} />}
      </span>
      <span className="tstep__main">
        <span className="tstep__title">{step.title}</span>
        {summary && <span className="tstep__sum" title={summary}>{summary}</span>}
      </span>
      <span className="tstep__side">
        {step.status === 'running' && <span className="tstep__live">Đang chạy</span>}
        {step.status === 'error' && <span className="tstep__fail">Lỗi</span>}
        {duration && <span className="tstep__dur tnum">{duration}</span>}
        {expandable && <Icon name={open ? 'chevronDown' : 'chevronRight'} size={14} className="tstep__chev" />}
      </span>
    </>
  )
  return (
    <li className={`tstep tstep--${step.status}`} data-kind={step.kind}>
      {expandable ? (
        <button type="button" className="tstep__row" aria-expanded={open} onClick={() => setOpen((value) => !value)}>{content}</button>
      ) : (
        <div className="tstep__row">{content}</div>
      )}
      {open && detail && (
        <div className="tstep__body">
          {detail.text && <p className="tstep__thought">{detail.text}</p>}
          {detail.arguments && Object.keys(detail.arguments).length > 0 && (
            <dl className="tstep__args">
              {Object.entries(detail.arguments).map(([name, value]) => (
                <div key={name}>
                  <dt>{name}</dt>
                  <dd>{argumentText(value)}</dd>
                </div>
              ))}
            </dl>
          )}
          {detail.result?.error && <p className="tstep__error">{detail.result.error}</p>}
          {detail.result?.documents && detail.result.documents.length > 0 && (
            <ul className="tstep__docs">
              {detail.result.documents.map((reference, index) => (
                <li key={`${reference.doc_id}-${index}`}>
                  <button type="button" className="tstep__doc" onClick={() => onOpenDocument(reference)}>
                    <Icon name="file" size={14} />
                    <span>{reference.label}</span>
                  </button>
                  {reference.section && <span className="tstep__section">{reference.section}</span>}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </li>
  )
}

/** Seconds since `start`, redrawn a few times per second. */
function useElapsed(start: number | undefined, active: boolean): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active || start === undefined) return
    setNow(Date.now())
    const timer = window.setInterval(() => setNow(Date.now()), 200)
    return () => window.clearInterval(timer)
  }, [active, start])
  return start === undefined ? 0 : Math.max(0, now - start)
}

/**
 * "Nhật ký xử lý": a collapsible strip with one context card per step (3 px accent in the status colour). While the turn runs it
 * is open and names what is being done right now; afterwards it folds into "N bước · 2,1 giây".
 */
export function TraceLog({ steps, running, startedAt, durationMs, outcome, onOpenDocument }: TraceLogProps) {
  const [manual, setManual] = useState<boolean | null>(null)
  const elapsed = useElapsed(startedAt, running)
  const [slow, setSlow] = useState(false)

  // The strip follows the turn (open while working, folded after) until the reader has chosen.
  useEffect(() => setManual(null), [running])
  useEffect(() => {
    if (!running || steps.length > 0) {
      setSlow(false)
      return
    }
    const timer = window.setTimeout(() => setSlow(true), 3000)
    return () => window.clearTimeout(timer)
  }, [running, steps.length])

  const open = manual ?? running
  const waiting = running && steps.length === 0
  const now = runningLabel(steps)
  const title = waiting ? 'Đang gửi yêu cầu' : running ? (now ? `Đang xử lý · ${now}` : 'Đang xử lý · tổng hợp câu trả lời') : 'Nhật ký xử lý'
  const total = running ? elapsed : durationMs
  const stats = running
    ? formatSeconds(elapsed)
    : [`${steps.length} bước`, outcome === 'stopped' ? 'đã dừng' : outcome === 'error' ? 'có lỗi' : formatSeconds(total)].join(' · ')
  const listId = `trace-${startedAt ?? steps[0]?.id ?? 'x'}`

  return (
    <section className={`trace trace--${running ? 'running' : outcome}`} aria-label="Nhật ký xử lý">
      <button type="button" className="trace__head" aria-expanded={open} aria-controls={listId} onClick={() => setManual(!open)}>
        <span className="trace__lead">
          {running ? <Icon name="spinner" size={16} className="spin" /> : <Icon name={open ? 'chevronDown' : 'chevronRight'} size={16} />}
        </span>
        <span className="trace__title">{title}</span>
        <span className="trace__stats tnum">{running ? stats : `· ${stats}`}</span>
      </button>
      {open && (
        <ol className="trace__list" id={listId}>
          {waiting && (
            <li className="tstep tstep--running">
              <div className="tstep__row">
                <span className="tstep__icon"><Icon name="spinner" size={18} className="spin" /></span>
                <span className="tstep__main">
                  <span className="tstep__title">{slow ? 'Trợ lý đang khởi động' : 'Chuẩn bị xử lý yêu cầu'}</span>
                  <span className="tstep__sum">{slow ? 'Lần đầu của một cuộc trò chuyện có thể mất khoảng 10 giây.' : 'Yêu cầu đã được gửi tới máy chủ.'}</span>
                </span>
                <span className="tstep__side"><span className="tstep__live">Đang chạy</span></span>
              </div>
            </li>
          )}
          {steps.map((step) => (
            <StepCard key={String(step.id)} step={step} onOpenDocument={onOpenDocument} />
          ))}
        </ol>
      )}
    </section>
  )
}
