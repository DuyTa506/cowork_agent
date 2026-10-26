import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import type { Citation, StepDocumentRef } from '../../api/chat'
import { Alert } from '../Alert'
import { Button } from '../Button'
import { Icon, type IconName } from '../Icon'
import { Spinner } from '../Spinner'
import { AssistantEntry, UserEntry } from './Entries'
import type { UiMessage } from './types'

export type StarterId = 'search' | 'summarize' | 'compose'

interface Starter {
  id: StarterId | 'check'
  icon: IconName
  title: string
  hint: string
}

const STARTERS: Starter[] = [
  { id: 'search', icon: 'search', title: 'Tra cứu văn bản', hint: 'Hỏi theo nội dung, số ký hiệu hoặc đơn vị; câu trả lời có trích dẫn nguồn.' },
  { id: 'summarize', icon: 'clipboard', title: 'Tóm tắt văn bản', hint: 'Tải tệp lên hoặc nêu tên văn bản trong kho để lấy ý chính.' },
  { id: 'compose', icon: 'canvas', title: 'Soạn công văn hoặc kế hoạch', hint: 'Bật Canvas và soạn theo thể thức Thông tư 68/2023/TT-BQP.' },
  { id: 'check', icon: 'shield', title: 'Kiểm tra thể thức', hint: 'Đối chiếu một tệp có sẵn với quy định trình bày văn bản.' },
]

interface TranscriptProps {
  messages: UiMessage[]
  /** Attachment id -> file name, for the chips under a question. */
  attachmentNames: ReadonlyMap<number, string>
  loading: boolean
  error: string | null
  /** A turn is running. */
  running: boolean
  /** The conversation has a draft (answers that worked on it offer to open it). */
  hasDraft: boolean
  onRetry: () => void
  onOpenCitation: (citation: Citation) => void
  onOpenDocument: (reference: StepDocumentRef) => void
  onStarter: (id: StarterId) => void
  /** Asks the last question again. */
  onRegenerate: (question: UiMessage) => void
  onOpenCanvas: () => void
}

const NEAR_BOTTOM = 96

/** An answer that created or changed the draft. */
const touchedDraft = (message: UiMessage): boolean => message.steps.some((step) => step.tool?.startsWith('canvas_') && step.tool !== 'canvas_read')

/**
 * The conversation as a staff log: hairline-separated entries, no bubbles. Follows new content while the reader is at the
 * bottom; scrolling up stops that and offers a "Tin mới" button.
 */
export function Transcript({ messages, attachmentNames, loading, error, running, hasDraft, onRetry, onOpenCitation, onOpenDocument, onStarter, onRegenerate, onOpenCanvas }: TranscriptProps) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const innerRef = useRef<HTMLDivElement>(null)
  const stick = useRef(true)
  const [away, setAway] = useState(false)
  const [unseen, setUnseen] = useState(false)

  const onScroll = () => {
    const element = scrollRef.current
    if (!element) return
    const near = element.scrollHeight - element.scrollTop - element.clientHeight < NEAR_BOTTOM
    stick.current = near
    setAway(!near)
    if (near) setUnseen(false)
  }

  const jump = useCallback(() => {
    const element = scrollRef.current
    if (!element) return
    stick.current = true
    setAway(false)
    setUnseen(false)
    element.scrollTo({ top: element.scrollHeight, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
  }, [])

  // Sending a message always brings the conversation to the end.
  const last = messages[messages.length - 1]
  const newTurn = last?.role === 'assistant' && last.status === 'running' && last.steps.length === 0
  useLayoutEffect(() => {
    if (!newTurn) return
    stick.current = true
    setAway(false)
    setUnseen(false)
    const element = scrollRef.current
    if (element) element.scrollTop = element.scrollHeight
  }, [newTurn, messages.length])

  // New steps and the answer reveal grow the content in place, so follow its size rather than React renders.
  useEffect(() => {
    const inner = innerRef.current
    if (!inner) return
    const follow = () => {
      const element = scrollRef.current
      if (!element) return
      if (stick.current) element.scrollTop = element.scrollHeight
      else setUnseen(true)
    }
    const observer = new ResizeObserver(follow)
    observer.observe(inner)
    follow()
    return () => observer.disconnect()
  }, [])

  const lastAnswerIndex = (() => {
    for (let index = messages.length - 1; index >= 0; index -= 1) if (messages[index]?.role === 'assistant') return index
    return -1
  })()

  return (
    <div className="thread-wrap">
      <div className="thread" ref={scrollRef} onScroll={onScroll} tabIndex={-1}>
        <div className="thread__inner" ref={innerRef}>
          {loading && <div className="page-loading"><Spinner label="Đang tải cuộc trò chuyện" size={24} /></div>}
          {error && (
            <Alert kind="error" title="Không tải được cuộc trò chuyện" action={<Button onClick={onRetry}>Thử lại</Button>}>
              {error}
            </Alert>
          )}
          {!loading && !error && messages.length === 0 && (
            <section className="welcome" aria-labelledby="welcome-title">
              <h2 className="welcome__title" id="welcome-title">Đồng chí cần tra cứu, tóm tắt hay soạn thảo văn bản?</h2>
              <p className="welcome__sub">Trợ lý chỉ tìm trong những văn bản đồng chí được phép xem, và luôn nêu rõ nguồn trích dẫn.</p>
              <ul className="starters" aria-label="Bắt đầu nhanh">
                {STARTERS.map((starter) => (
                  <li key={starter.id}>
                    {starter.id === 'check' ? (
                      <Link className="starter" to="/kiem-tra">
                        <StarterBody starter={starter} />
                      </Link>
                    ) : (
                      <button type="button" className="starter" onClick={() => onStarter(starter.id as StarterId)}>
                        <StarterBody starter={starter} />
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}
          {messages.map((message, index) => {
            if (message.role === 'user') return <UserEntry key={message.key} message={message} attachmentNames={attachmentNames} />
            const question = messages[index - 1]?.role === 'user' ? messages[index - 1] : undefined
            return (
              <AssistantEntry
                key={message.key}
                message={message}
                question={question}
                attachmentNames={attachmentNames}
                canRegenerate={index === lastAnswerIndex && Boolean(question) && message.status !== 'running'}
                busy={running}
                canOpenCanvas={hasDraft && touchedDraft(message)}
                onOpenCitation={onOpenCitation}
                onOpenDocument={onOpenDocument}
                onRegenerate={() => question && onRegenerate(question)}
                onOpenCanvas={onOpenCanvas}
              />
            )
          })}
        </div>
      </div>
      {away && (
        <button type="button" className={unseen ? 'jump jump--new' : 'jump'} onClick={jump}>
          <Icon name="arrowDown" size={16} />
          {unseen ? 'Tin mới' : 'Về cuối'}
        </button>
      )}
    </div>
  )
}

function StarterBody({ starter }: { starter: Starter }) {
  return (
    <>
      <span className="starter__icon"><Icon name={starter.icon} size={20} /></span>
      <span className="starter__text">
        <span className="starter__title">{starter.title}</span>
        <span className="starter__hint">{starter.hint}</span>
      </span>
      <Icon name="chevronRight" size={16} className="starter__go" />
    </>
  )
}
