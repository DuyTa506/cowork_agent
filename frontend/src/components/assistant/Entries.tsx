import { useState } from 'react'
import type { Citation, StepDocumentRef } from '../../api/chat'
import { formatDate, formatTime } from '../../lib/format'
import { Alert } from '../Alert'
import { Button } from '../Button'
import { FileTypeBadge } from '../FileTypeBadge'
import { Icon } from '../Icon'
import { CitationChip } from './CitationChip'
import { turnDuration } from './log'
import { Markdown } from './Markdown'
import { SourceCards } from './SourceCards'
import { TraceLog } from './TraceLog'
import type { UiMessage } from './types'
import { useReveal } from './useReveal'

/** Time of an entry; entries of other days also carry the date. */
function stamp(createdAt: string): string {
  const time = formatTime(createdAt)
  const date = new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(createdAt) ? createdAt : `${createdAt}Z`)
  const today = new Date()
  const sameDay = date.getFullYear() === today.getFullYear() && date.getMonth() === today.getMonth() && date.getDate() === today.getDate()
  return sameDay ? time : `${formatDate(date.toISOString().slice(0, 10), '')} ${time}`.trim()
}

/** Copies text to the clipboard; the async API needs a secure context, so fall back to a hidden textarea. */
async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    const area = document.createElement('textarea')
    area.value = text
    area.style.position = 'fixed'
    area.style.opacity = '0'
    document.body.appendChild(area)
    area.select()
    const ok = document.execCommand('copy')
    area.remove()
    return ok
  }
}

function EntryLabel({ who, ai, time }: { who: string; ai?: boolean; time: string }) {
  return (
    <header className="entry__label">
      <span className={ai ? 'entry__role entry__role--ai' : 'entry__role'}>{who}</span>
      <time className="entry__time tnum">{time}</time>
    </header>
  )
}

interface UserEntryProps {
  message: UiMessage
  attachmentNames: ReadonlyMap<number, string>
}

/** "ĐỒNG CHÍ": the question, with its attached files as file-type badges. */
export function UserEntry({ message, attachmentNames }: UserEntryProps) {
  return (
    <article className="entry entry--user" aria-label="Câu hỏi của đồng chí">
      <EntryLabel who="Đồng chí" time={stamp(message.created_at)} />
      {message.attachment_ids.length > 0 && (
        <ul className="entry__files" aria-label="Tệp đính kèm">
          {message.attachment_ids.map((id) => {
            const name = attachmentNames.get(id) ?? `Tệp ${id}`
            return (
              <li key={id} className="entry__file">
                <FileTypeBadge name={attachmentNames.get(id) ?? ''} size="sm" />
                <span className="entry__file-name" title={name}>{name}</span>
              </li>
            )
          })}
        </ul>
      )}
      <p className="entry__text">{message.content}</p>
    </article>
  )
}

interface AssistantEntryProps {
  message: UiMessage
  /** The question this entry answers (for the time the answer took). */
  question?: UiMessage
  attachmentNames: ReadonlyMap<number, string>
  /** Only the latest answer can be asked for again. */
  canRegenerate: boolean
  /** A turn is running: actions that start another one wait. */
  busy: boolean
  /** The conversation has a draft and this answer worked on it. */
  canOpenCanvas: boolean
  onOpenCitation: (citation: Citation) => void
  onOpenDocument: (reference: StepDocumentRef) => void
  onRegenerate: () => void
  onOpenCanvas: () => void
}

/** "TRỢ LÝ AI": the processing log, the answer typeset like a document, its numbered sources and actions. */
export function AssistantEntry({ message, question, attachmentNames, canRegenerate, busy, canOpenCanvas, onOpenCitation, onOpenDocument, onRegenerate, onOpenCanvas }: AssistantEntryProps) {
  // A failed turn keeps its error text in `content` when loaded from the server; it is shown as an alert instead.
  const failed = message.status === 'error'
  const answer = failed ? '' : message.content
  const errorText = message.error ?? (failed ? message.content : '')
  const running = message.status === 'running'
  const { shown, done, skip } = useReveal(answer, Boolean(message.fresh))
  const [copied, setCopied] = useState(false)
  const [rating, setRating] = useState<'up' | 'down' | null>(null)
  const byNumber = new Map(message.citations.map((citation) => [citation.n, citation]))
  const finished = !running && done
  const outcome = running ? 'running' : message.status === 'running' ? 'done' : message.status

  const copy = async () => {
    if (await copyText(message.content.replace(/\s*\[\d{1,3}\]/g, ''))) {
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1800)
    }
  }

  const showTrace = message.steps.length > 0 || running
  return (
    <article className="entry entry--ai" aria-label="Trợ lý AI trả lời" aria-busy={running || undefined}>
      <EntryLabel who="Trợ lý AI" ai time={stamp(message.created_at)} />
      {showTrace && (
        <TraceLog
          steps={message.steps}
          running={running}
          startedAt={message.startedAt}
          durationMs={turnDuration(message, question)}
          outcome={outcome}
          onOpenDocument={onOpenDocument}
        />
      )}
      {shown && (
        <div className={done ? 'answer' : 'answer answer--reveal'} onClick={done ? undefined : skip} title={done ? undefined : 'Nhấn để hiện toàn bộ'}>
          <Markdown
            text={shown}
            renderCitation={(n, key) => {
              const citation = byNumber.get(n)
              return citation ? <CitationChip key={key} citation={citation} onOpen={onOpenCitation} /> : `[${n}]`
            }}
          />
        </div>
      )}
      {errorText && (
        <div className="entry__error">
          <Alert kind="error" action={canRegenerate && !busy ? <Button icon="refresh" onClick={onRegenerate}>Thử lại</Button> : undefined}>{errorText}</Alert>
        </div>
      )}
      {message.status === 'stopped' && (
        <p className="entry__note"><Icon name="stop" size={14} />Đã dừng trả lời{answer || message.steps.length === 0 ? '.' : '. Các bước đã làm được giữ lại ở trên.'}</p>
      )}
      {finished && message.citations.length > 0 && <SourceCards citations={message.citations} attachmentNames={attachmentNames} onOpen={onOpenCitation} />}
      {finished && (answer || canOpenCanvas) && (
        <div className="acts" role="group" aria-label="Thao tác với câu trả lời">
          {answer && (
            <button type="button" className="acts__btn" onClick={() => void copy()}>
              <Icon name={copied ? 'check' : 'copy'} size={16} />
              {copied ? 'Đã sao chép' : 'Sao chép'}
            </button>
          )}
          {canRegenerate && (
            <button type="button" className="acts__btn" disabled={busy} onClick={onRegenerate}>
              <Icon name="refresh" size={16} />
              Tạo lại
            </button>
          )}
          {canOpenCanvas && (
            <button type="button" className="acts__btn acts__btn--accent" onClick={onOpenCanvas}>
              <Icon name="canvas" size={16} />
              Mở trong Canvas
            </button>
          )}
          {answer && (
            <span className="acts__rate" role="group" aria-label="Đánh giá câu trả lời">
              <button type="button" className="acts__btn" aria-pressed={rating === 'up'} onClick={() => setRating(rating === 'up' ? null : 'up')}>
                <Icon name="thumbUp" size={16} />
                Hữu ích
              </button>
              <button type="button" className="acts__btn" aria-pressed={rating === 'down'} onClick={() => setRating(rating === 'down' ? null : 'down')}>
                <Icon name="thumbDown" size={16} />
                Chưa đúng
              </button>
            </span>
          )}
        </div>
      )}
      <div className="sr-only" role="status">{finished && answer ? 'Trợ lý đã trả lời.' : ''}</div>
    </article>
  )
}
