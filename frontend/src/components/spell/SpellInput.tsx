import { useEffect, useRef, useState, type DragEvent } from 'react'
import { spellCheckApi } from '../../api'
import type { SpellOptions, SpellSession } from '../../api/spellCheck'
import { useAsyncData } from '../../hooks/useAsyncData'
import { formatFileSize } from '../../lib/format'
import { Button } from '../Button'
import { describeFailure, type FailureText } from '../check/model'
import { FailureNotice } from '../check/Notice'
import { FileTypeBadge } from '../FileTypeBadge'
import { Icon } from '../Icon'
import { Spinner } from '../Spinner'
import { Switch } from '../Switch'

const FALLBACK_ACCEPT = ['.docx', '.doc', '.pdf', '.txt', '.md']
const FALLBACK_MAX_CHARS = 200000

interface SpellInputProps {
  onChecked: (session: SpellSession) => void
}

type Phase = 'idle' | 'text' | 'file'

const normalizeExtension = (value: string) => (value.startsWith('.') ? value : `.${value}`).toLowerCase()
const formatCount = (value: number) => value.toLocaleString('vi-VN')

// What was typed survives going to another screen and back (and nothing else does); it is never stored anywhere.
const draft = { text: '', markdown: false }

const STEPS = [
  { title: 'Dán văn bản hoặc chọn tệp', text: 'Word, PDF có lớp chữ, .txt hoặc .md.' },
  { title: 'Xem các từ nghi sai', text: 'Gạch sóng trên văn bản, kèm gợi ý và độ tin cậy.' },
  { title: 'Chọn, sửa và tải về', text: 'Chỉ sửa những chỗ bạn đồng ý; bỏ qua từ đúng.' },
]

/** First screen: type or paste text, or choose / drop one file; either is checked straight away. */
export function SpellInput({ onChecked }: SpellInputProps) {
  const fileRef = useRef<HTMLInputElement>(null)
  const { data: options } = useAsyncData((signal) => spellCheckApi.getOptions(signal), [])
  const [text, setText] = useState(draft.text)
  const [markdown, setMarkdown] = useState(draft.markdown)
  const [dragging, setDragging] = useState(false)
  const [phase, setPhase] = useState<Phase>('idle')
  const [progress, setProgress] = useState(0)
  const [picked, setPicked] = useState<{ name: string; size: number } | null>(null)
  const [failure, setFailure] = useState<FailureText | null>(null)

  const accept = options?.accept.map(normalizeExtension) ?? FALLBACK_ACCEPT
  const maxChars = options?.max_chars ?? FALLBACK_MAX_CHARS
  const busy = phase !== 'idle'
  const tooLong = text.length > maxChars

  useEffect(() => {
    draft.text = text
    draft.markdown = markdown
  }, [text, markdown])

  // Leaving the screen mid-request must not update a component that is gone (and the result must not stay on the server).
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])

  const done = (session: SpellSession) => {
    if (mounted.current) onChecked(session)
    else spellCheckApi.discardSession(session.id)
  }

  const runText = async () => {
    if (busy) return
    if (!text.trim()) {
      setFailure({ title: 'Chưa có văn bản', message: 'Hãy dán hoặc gõ văn bản vào ô, hoặc chọn một tệp.', kind: 'empty' })
      return
    }
    setFailure(null)
    setPhase('text')
    try {
      done(await spellCheckApi.checkText(text, markdown))
    } catch (error) {
      if (!mounted.current) return
      setFailure(describeFailure(error, 'Không soát được chính tả'))
      setPhase('idle')
    }
  }

  const runFile = async (incoming: FileList | File[]) => {
    const list = Array.from(incoming)
    const file = list[0]
    if (!file || busy) return
    const problem = validate(file, accept, options)
    if (problem) {
      setFailure(problem)
      return
    }
    setFailure(null)
    setPicked({ name: file.name, size: file.size })
    setProgress(0)
    setPhase('file')
    try {
      done(await spellCheckApi.uploadFile(file, markdown || undefined, setProgress))
    } catch (error) {
      if (!mounted.current) return
      setFailure(describeFailure(error, 'Không soát được tệp'))
      setPhase('idle')
    }
  }

  const onDrop = (event: DragEvent) => {
    event.preventDefault()
    setDragging(false)
    void runFile(event.dataTransfer.files)
  }

  const choose = () => {
    if (!busy) fileRef.current?.click()
  }

  const sentAll = phase === 'file' && progress >= 1
  const step = phase === 'idle' ? 0 : phase === 'text' || sentAll ? 1 : 0

  return (
    <div className="check check--upload spell">
      <header className="check-head">
        <h1 className="check-head__title">Kiểm tra chính tả</h1>
        <p className="check-head__desc">Soát lỗi chính tả tiếng Việt: sai dấu thanh, âm tiết không hợp lệ, từ viết sai, thừa dấu cách, dấu câu.</p>
        <p className="check-info">
          <Icon name="shield" size={18} />
          <span>
            Văn bản và tệp chỉ lưu tạm trong thư mục riêng của bạn, không lập chỉ mục, không vào kho văn bản
            {options ? `; tự xóa sau ${options.retention_hours} giờ` : ''}.
          </span>
        </p>
      </header>

      <div className="check-upload">
        <div className="check-upload__main">
          {failure && <FailureNotice failure={failure} actions={failure.kind === 'network' ? undefined : <Button icon="upload" onClick={choose}>Chọn tệp</Button>} />}

          <section className="spell-text" aria-label="Văn bản cần soát">
            <label className="spell-text__label" htmlFor="spell-text">Dán hoặc gõ văn bản</label>
            <textarea
              id="spell-text"
              className="spell-text__box"
              spellCheck={false}
              rows={10}
              placeholder="Dán hoặc gõ văn bản vào đây…"
              value={text}
              disabled={busy}
              onChange={(event) => { setText(event.target.value); if (failure) setFailure(null) }}
            />
            <div className="spell-text__foot">
              <Button variant="primary" icon="spellcheck" loading={phase === 'text'} disabled={busy || !text.trim() || tooLong} onClick={runText}>
                Soát chính tả
              </Button>
              <span className={tooLong ? 'spell-text__count spell-text__count--over tnum' : 'spell-text__count tnum'}>
                {formatCount(text.length)} / {formatCount(maxChars)} ký tự
              </span>
              {text && !busy && <Button variant="ghost" onClick={() => { setText(''); setFailure(null) }}>Xóa hết</Button>}
              <span className="spacer" />
              <Switch checked={markdown} onChange={setMarkdown} label="Bỏ qua mã và liên kết Markdown" disabled={busy} />
            </div>
          </section>

          <p className="spell-or"><span>hoặc</span></p>

          <div
            className={['check-drop', 'spell-drop', dragging && 'check-drop--over', phase === 'file' && 'check-drop--busy'].filter(Boolean).join(' ')}
            aria-busy={phase === 'file'}
            onClick={choose}
            onDragOver={(event) => { event.preventDefault(); if (!busy) setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
          >
            {phase === 'file' && picked ? (
              <div className="check-drop__busy" aria-live="polite">
                <FileTypeBadge name={picked.name} size="lg" />
                <strong className="check-drop__file">{picked.name}</strong>
                <span className="check-drop__size">{formatFileSize(picked.size)}</span>
                <div
                  className={sentAll ? 'check-progress check-progress--busy' : 'check-progress'}
                  role="progressbar"
                  aria-label="Tiến độ soát chính tả"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={sentAll ? undefined : Math.round(progress * 100)}
                >
                  <div className="check-progress__fill" style={{ width: `${progress * 100}%` }} />
                </div>
                <p className="check-drop__status">
                  <Spinner />
                  {sentAll ? 'Đang soát chính tả. Văn bản dài có thể mất vài chục giây.' : `Đang tải lên… ${Math.round(progress * 100)}%`}
                </p>
              </div>
            ) : (
              <>
                <div className="check-drop__types" aria-hidden="true">
                  {['mau.docx', 'mau.pdf', 'mau.txt'].map((name) => <FileTypeBadge key={name} name={name} size="lg" />)}
                </div>
                <h2 className="spell-drop__title">Kéo thả hoặc chọn tệp</h2>
                <p className="check-drop__hint">
                  <span className="tnum">{accept.join(' ')}</span>
                  {options ? <> · tối đa <span className="tnum">{options.max_mb} MB</span></> : null}
                </p>
                <Button variant="default" icon="upload" className="check-drop__button" onClick={(event) => { event.stopPropagation(); choose() }}>
                  Chọn tệp từ máy
                </Button>
              </>
            )}
            <input
              ref={fileRef}
              type="file"
              hidden
              accept={accept.join(',')}
              onClick={(event) => event.stopPropagation()}
              onChange={(event) => {
                if (event.target.files) void runFile(event.target.files)
                event.target.value = ''
              }}
            />
          </div>
        </div>

        <aside className="check-card check-options" aria-label="Cách làm việc">
          <h2 className="check-card__title">Cách sửa theo loại tệp</h2>
          <dl className="spell-kinds">
            <dt>Word (.docx, .doc)</dt>
            <dd>Sửa vào tệp, lưu thành bản mới “_sua.docx”. Mỗi chỗ sửa có thể ghi dấu Track Changes để duyệt trong Word.</dd>
            <dt>Văn bản dán, .txt, .md</dt>
            <dd>Sửa ngay trên màn này; chép văn bản hoặc tải về “_sua” cùng đuôi tệp.</dd>
            <dt>PDF có lớp chữ</dt>
            <dd>Chỉ liệt kê lỗi và tải báo cáo; sửa ở tệp gốc rồi xuất lại PDF. Bản scan chưa soát được.</dd>
          </dl>
          <p className="check-field__help">Từ nghi sai nhưng bạn thấy đúng (tên riêng, thuật ngữ) bấm “Bỏ qua”: từ đó không báo lại trong lần soát này.</p>
        </aside>

        <ol className="check-steps" aria-label="Các bước">
          {STEPS.map((item, index) => {
            const state = index < step ? 'done' : index === step ? 'current' : 'todo'
            return (
              <li key={item.title} className={`check-step check-step--${state}`} aria-current={state === 'current' ? 'step' : undefined}>
                <span className="check-step__num">{state === 'done' ? <Icon name="check" size={16} /> : index + 1}</span>
                <span className="check-step__text">
                  <strong>{item.title}</strong>
                  <span>{item.text}</span>
                </span>
                {index < STEPS.length - 1 && <Icon name="arrowRight" size={16} className="check-step__arrow" />}
              </li>
            )
          })}
        </ol>
      </div>
    </div>
  )
}

/** Quick checks before upload so obvious mistakes do not wait for a round trip. */
function validate(file: File, accept: string[], options: SpellOptions | null): FailureText | null {
  const lower = file.name.toLowerCase()
  if (!accept.some((extension) => lower.endsWith(extension))) {
    return { title: 'Định dạng tệp chưa được hỗ trợ', message: `“${file.name}” không phải tệp ${accept.join(', ')}.`, kind: 'unsupported' }
  }
  if (file.size === 0) return { title: 'Tệp rỗng', message: `“${file.name}” không có nội dung.`, kind: 'empty' }
  if (options && file.size > options.max_mb * 1024 * 1024) {
    return { title: 'Tệp quá lớn', message: `“${file.name}” (${formatFileSize(file.size)}) vượt quá giới hạn ${options.max_mb} MB.`, kind: 'too_large' }
  }
  return null
}
