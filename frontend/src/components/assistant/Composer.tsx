import { useEffect, useId, useRef, useState, type ClipboardEvent, type DragEvent, type KeyboardEvent } from 'react'
import { formatFileSize } from '../../lib/format'
import { FileTypeBadge } from '../FileTypeBadge'
import { Icon } from '../Icon'
import { PopMenu } from './PopMenu'
import type { ComposerFile } from './types'

export const ACCEPTED_EXTENSIONS = ['.doc', '.docx', '.pdf']

interface ComposerProps {
  files: ComposerFile[]
  canvasOn: boolean
  running: boolean
  /** The Stop button was pressed and the server has not ended the turn yet. */
  stopping?: boolean
  /** Blocks sending (for example while a conversation is loading). */
  disabled?: boolean
  placeholder?: string
  /** Replaces the text box content when `nonce` changes (a starter was chosen). */
  prefill: { text: string; nonce: number } | null
  onCanvasChange: (on: boolean) => void
  onAddFiles: (files: File[]) => void
  onRemoveFile: (key: string) => void
  /** The box was focused or typed in: get the assistant ready. */
  onWarm: () => void
  onSend: (text: string) => void
  onStop: () => void
}

type FileTone = 'busy' | 'ok' | 'bad'

/** What a file chip says about its state: always a label and an icon, never colour alone. */
function fileStatus(file: ComposerFile): { label: string; detail: string; tone: FileTone } {
  if (file.error) return { label: 'Lỗi', detail: file.error, tone: 'bad' }
  const attachment = file.attachment
  if (!attachment) return { label: 'Đang tải lên', detail: `${Math.round(file.progress * 100)}%`, tone: 'busy' }
  switch (attachment.state) {
    case 'queued':
      return { label: 'Đang xử lý', detail: 'Đang chờ lập chỉ mục', tone: 'busy' }
    case 'processing':
      return { label: 'Đang xử lý', detail: 'Đang lập chỉ mục', tone: 'busy' }
    case 'ready':
      return { label: 'Sẵn sàng', detail: 'Chỉ dùng trong cuộc trò chuyện này', tone: 'ok' }
    default:
      return { label: 'Lỗi', detail: attachment.detail || 'Không lập chỉ mục được tệp', tone: 'bad' }
  }
}

/** An attached file in the composer: type badge, name and its state in words, icon and colour. */
function FileChip({ file, onRemove }: { file: ComposerFile; onRemove: () => void }) {
  const status = fileStatus(file)
  return (
    <li className={`atch atch--${status.tone}`} title={`${file.name} · ${formatFileSize(file.size)} · ${status.detail}`}>
      <FileTypeBadge name={file.name} size="sm" />
      <span className="atch__name">{file.name}</span>
      <span className="atch__state" role={status.tone === 'bad' ? 'alert' : 'status'}>
        <Icon name={status.tone === 'ok' ? 'checkCircle' : status.tone === 'bad' ? 'alertCircle' : 'spinner'} size={16} className={status.tone === 'busy' ? 'spin' : undefined} />
        {status.label}
        {status.tone === 'busy' && !file.attachment && <span className="tnum"> {Math.round(file.progress * 100)}%</span>}
      </span>
      <button type="button" className="atch__x" aria-label={`Bỏ tệp ${file.name}`} title="Bỏ tệp" onClick={onRemove}>
        <Icon name="close" size={14} />
      </button>
    </li>
  )
}

/**
 * Message box: a bordered card with the text on top and a toolbar beneath it: "+" menu (upload a file, switch Canvas on),
 * chips for Canvas and attached files, Send / Stop on the right. Enter sends, Shift+Enter breaks the line; files can be
 * dropped or pasted.
 */
export function Composer({ files, canvasOn, running, stopping = false, disabled = false, placeholder, prefill, onCanvasChange, onAddFiles, onRemoveFile, onWarm, onSend, onStop }: ComposerProps) {
  const [text, setText] = useState('')
  const [dragging, setDragging] = useState(false)
  const areaRef = useRef<HTMLTextAreaElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const labelId = useId()

  const notReady = files.some((file) => file.attachment?.state !== 'ready')
  const broken = files.some((file) => file.error || file.attachment?.state === 'failed')
  const canSend = !running && !disabled && !notReady && text.trim().length > 0

  useEffect(() => {
    if (!prefill) return
    setText(prefill.text)
    const area = areaRef.current
    area?.focus()
    window.requestAnimationFrame(() => area?.setSelectionRange(prefill.text.length, prefill.text.length))
    onWarm()
    // Only a new nonce is a new prefill.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefill])

  // Grow with the text up to a limit.
  useEffect(() => {
    const area = areaRef.current
    if (!area) return
    area.style.height = 'auto'
    area.style.height = `${Math.min(area.scrollHeight, 220)}px`
  }, [text])

  const send = () => {
    if (!canSend) return
    onSend(text.trim())
    setText('')
  }

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter while composing Vietnamese (Telex/VNI) confirms the word and must not send.
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      send()
    }
  }

  const hasFiles = (event: DragEvent) => Array.from(event.dataTransfer.types).includes('Files')
  const onDragOver = (event: DragEvent) => {
    if (!hasFiles(event)) return
    event.preventDefault()
    setDragging(true)
  }
  const onDrop = (event: DragEvent) => {
    if (!hasFiles(event)) return
    event.preventDefault()
    setDragging(false)
    onAddFiles(Array.from(event.dataTransfer.files))
  }
  const onPaste = (event: ClipboardEvent) => {
    const pasted = Array.from(event.clipboardData.files)
    if (pasted.length > 0) {
      event.preventDefault()
      onAddFiles(pasted)
    }
  }

  return (
    <div className="comp">
      <div
        className={dragging ? 'comp__card comp__card--drag' : 'comp__card'}
        onDragEnter={onDragOver}
        onDragOver={onDragOver}
        onDragLeave={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false)
        }}
        onDrop={onDrop}
      >
        <label className="sr-only" htmlFor={labelId}>Nội dung yêu cầu</label>
        <textarea
          id={labelId}
          ref={areaRef}
          className="comp__text"
          rows={2}
          value={text}
          placeholder={placeholder ?? 'Hỏi về văn bản, yêu cầu tóm tắt hoặc soạn thảo…'}
          onChange={(event) => {
            setText(event.target.value)
            if (event.target.value) onWarm()
          }}
          onFocus={onWarm}
          onKeyDown={onKeyDown}
          onPaste={onPaste}
        />
        <div className="comp__bar">
          <PopMenu
            label="Thêm vào cuộc trò chuyện"
            placement="top"
            align="start"
            items={[
              { key: 'upload', label: 'Tải tệp lên', icon: 'upload', hint: '.docx, .doc, .pdf · chỉ dùng trong cuộc này', onSelect: () => inputRef.current?.click() },
              { key: 'canvas', label: 'Canvas', icon: 'canvas', hint: 'Soạn văn bản theo mẫu thể thức', checked: canvasOn, onSelect: () => onCanvasChange(!canvasOn) },
            ]}
            trigger={(props) => (
              <button {...props} type="button" className="comp__plus" aria-label="Thêm tệp hoặc công cụ" title="Thêm tệp hoặc công cụ">
                <Icon name="plus" size={20} />
              </button>
            )}
          />
          <input
            ref={inputRef}
            type="file"
            hidden
            multiple
            accept={ACCEPTED_EXTENSIONS.join(',')}
            onChange={(event) => {
              onAddFiles(Array.from(event.target.files ?? []))
              event.target.value = ''
            }}
          />
          {(canvasOn || files.length > 0) && (
            <ul className="comp__chips" aria-label="Đính kèm và công cụ">
              {canvasOn && (
                <li className="tool-chip">
                  <Icon name="canvas" size={16} />
                  <span>Canvas</span>
                  <button type="button" className="tool-chip__x" aria-label="Tắt Canvas" title="Tắt Canvas" onClick={() => onCanvasChange(false)}>
                    <Icon name="close" size={14} />
                  </button>
                </li>
              )}
              {files.map((file) => (
                <FileChip key={file.key} file={file} onRemove={() => onRemoveFile(file.key)} />
              ))}
            </ul>
          )}
          <span className="comp__spacer" />
          {notReady && (
            <span className="comp__hint" role="status">{broken ? 'Bỏ tệp bị lỗi để gửi' : 'Chờ tệp xử lý xong để gửi'}</span>
          )}
          {running ? (
            <button type="button" className="comp__send comp__send--stop" aria-label={stopping ? 'Đang dừng' : 'Dừng trả lời'} title={stopping ? 'Đang dừng…' : 'Dừng trả lời'} disabled={stopping} onClick={onStop}>
              <Icon name="stop" size={16} />
            </button>
          ) : (
            <button type="button" className="comp__send" aria-label="Gửi" title="Gửi (Enter)" disabled={!canSend} onClick={send}>
              <Icon name="send" size={20} strokeWidth={2.25} />
            </button>
          )}
        </div>
        {dragging && <div className="comp__drop" aria-hidden="true">Thả tệp .docx, .doc hoặc .pdf để đính kèm</div>}
      </div>
      <p className="comp__foot">AI chỉ hỗ trợ người dùng, không đưa ra quyết định. Các đồng chí tự chịu trách nhiệm về văn bản của mình.</p>
    </div>
  )
}
