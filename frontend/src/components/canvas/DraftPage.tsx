import { Fragment, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import type { ChatDraft, DraftBlock, DraftField, SelectionContext, TableSpec } from '../../api/chat'
import { Button } from '../Button'
import { Chip } from '../Chip'
import { Icon } from '../Icon'
import { IconButton } from '../IconButton'
import { diffWords, type DiffPart } from './diff'
import { TableDiffView, TableEditor, TableMarked } from './DraftTable'
import { InlineEditor } from './InlineEditor'
import { ASK_PROMPTS, SelectionToolbar, useBlockSelection, type AskAction } from './SelectionToolbar'
import { describeDiff, diffTables } from './table'

interface DraftPageProps {
  draft: ChatDraft
  /** True while the assistant is working on the draft: the page cannot be edited. */
  locked: boolean
  onEditField: (key: string, text: string) => Promise<void>
  onEditBlock: (id: string, text: string) => Promise<void>
  /** Saves the whole edited spec of a table block. */
  onEditTable: (id: string, table: TableSpec) => Promise<void>
  /** Dismisses a passage's "figures changed" mark. */
  onReviewed: (id: string) => Promise<void>
  onDeleteBlock: (id: string) => Promise<void>
  /** Inserts a paragraph with `text` after `after` (null = at the start); resolves with the new draft, or null when it failed. */
  onInsertBlock: (after: string | null, text: string) => Promise<ChatDraft | null>
  onAccept: (id: string) => Promise<void>
  onReject: (id: string) => Promise<void>
  /** The user chose an action on selected text. */
  onAsk: (prompt: string, context: SelectionContext) => void
}

/** Places that can be edited in the page: a header field or a block. */
type EditTarget = `f:${string}` | `b:${string}`

/** Fields whose text the circular fixes; the other system fields (issuing body, number symbol) are a guess the user may correct. */
const FIXED_FIELDS = new Set(['quoc_hieu', 'tieu_ngu', 'ten_loai'])

const ownerClass = (field: DraftField): string => {
  if (field.owner === 'system') return 'cv-f cv-f--system'
  // `needs_input` also holds while the text still has "…" placeholders (the date line), so it is not only about empty fields.
  if (field.needs_input) return 'cv-f cv-f--need'
  return field.owner === 'assistant' ? 'cv-f cv-f--assistant' : 'cv-f cv-f--user'
}

/** What the field shows on the page: the label as a placeholder while empty, and the fixed lead-ins of some fields. */
function displayText(name: string, field: DraftField, docType: string): string {
  const text = field.text.trim()
  if (!text) return field.label
  if (name === 'trich_yeu' && docType === 'CV' && !/^v\/v\b/i.test(text)) return `V/v ${text}`
  if (name === 'kinh_gui' && !/^kính gửi/i.test(text)) return `Kính gửi: ${text}`
  return field.text
}

/** The line under an appendix title, as the Word export writes it: "(Kèm theo Công văn số …/… ngày … của …)". */
function attachedTo(draft: ChatDraft): string {
  const text = (key: string) => draft.fields[key]?.text.trim() ?? ''
  const number = (text('so_ky_hieu') || '…/…').replace(/^\s*số\s*:?\s*/i, '')
  const dated = /ngày.*$/.exec(text('dia_danh_ngay'))?.[0] ?? 'ngày … tháng … năm …'
  const issuer = text('co_quan_ban_hanh').toLowerCase().replace(/^./, (c) => c.toUpperCase())
  return `(Kèm theo ${draft.template.name} số ${number} ${dated}${issuer && issuer !== '…' ? ` của ${issuer}` : ''})`
}

function Lines({ text }: { text: string }) {
  const lines = text.split('\n')
  return (
    <>
      {lines.map((line, index) => (
        <span key={index}>
          {index > 0 && <br />}
          {line}
        </span>
      ))}
    </>
  )
}

/**
 * The draft laid out like a real TT68 document. Header and footer fields and the content blocks are styled by who
 * owns them (system: dotted underline, assistant: light background, user/needs input: dashed). Every part but the
 * quốc hiệu, tiêu ngữ and kind name can be edited by clicking; a proposal from the assistant shows as a diff with
 * Accept / Reject; selecting text in a block offers the quick requests (rewrite, shorten, military style, spelling).
 * Tables are edited cell by cell; appendices follow the signature, each from a new page.
 */
export function DraftPage({ draft, locked, onEditField, onEditBlock, onEditTable, onReviewed, onDeleteBlock, onInsertBlock, onAccept, onReject, onAsk }: DraftPageProps) {
  const [editing, setEditing] = useState<EditTarget | null>(null)
  const [busyBlock, setBusyBlock] = useState<string | null>(null)
  /** A new paragraph being typed; it exists only on this page until it has text (the server refuses empty paragraphs). */
  const [inserting, setInserting] = useState<{ after: string | null; text: string; attempt: number } | null>(null)
  const pageRef = useRef<HTMLElement>(null)
  const scrollRef = useRef<HTMLElement | null>(null)
  const [selection, clearSelection] = useBlockSelection(pageRef, scrollRef)
  const docType = draft.template.doc_type
  const fields = draft.fields

  const field = (name: string, options: { className?: string; as?: 'span' | 'div' } = {}): ReactNode => {
    const value = fields[name]
    if (!value) return null
    const target: EditTarget = `f:${name}`
    const editable = !FIXED_FIELDS.has(name) && !locked
    if (editing === target) {
      return (
        <InlineEditor
          value={value.text}
          label={value.label}
          multiline={value.multiline}
          className={options.className}
          onCommit={(text) => {
            setEditing(null)
            void onEditField(name, text)
          }}
          onCancel={() => setEditing(null)}
        />
      )
    }
    const open = () => editable && setEditing(target)
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault()
        open()
      }
    }
    const empty = !value.text.trim()
    const classes = [ownerClass(value), options.className, empty && 'cv-f--empty', editable && 'cv-f--editable'].filter(Boolean).join(' ')
    return (
      <span
        className={classes}
        data-field={name}
        {...(editable ? { role: 'button', tabIndex: 0, 'aria-label': `Sửa ${value.label}`, onClick: open, onKeyDown } : {})}
      >
        <Lines text={displayText(name, value, docType)} />
      </span>
    )
  }

  const blockView = (block: DraftBlock) => {
    const target: EditTarget = `b:${block.id}`
    const busy = busyBlock === block.id
    const run = async (action: () => Promise<void>) => {
      setBusyBlock(block.id)
      try {
        await action()
      } finally {
        setBusyBlock(null)
      }
    }
    if (editing === target && block.kind !== 'table') {
      return (
        <div key={block.id} className={`cv-block cv-block--${block.kind}`}>
          <InlineEditor
            value={block.text}
            label={block.kind === 'appendix' ? 'Tên phụ lục' : 'Nội dung đoạn'}
            onCommit={(text) => {
              setEditing(null)
              // An emptied paragraph is not saved (the server refuses it); removing one is the trash button.
              if (text.trim()) void onEditBlock(block.id, text)
            }}
            onCancel={() => setEditing(null)}
          />
        </div>
      )
    }
    if (block.proposal) {
      const { action, note } = block.proposal
      const proposed = block.proposal.table
      const isTable = block.kind === 'table' || Boolean(proposed)
      let shown: ReactNode
      let lead: string
      if (isTable) {
        const current = block.table
        if (action === 'delete' && current) shown = <TableMarked spec={current} mark="del" />
        else if (proposed && (action === 'insert' || !current)) shown = <TableMarked spec={proposed} mark="ins" />
        else if (proposed && current) shown = <TableDiffView before={current} after={proposed} />
        const changes = action === 'replace' && proposed && current ? describeDiff(diffTables(current, proposed)) : ''
        lead = action === 'delete' ? 'Đề xuất xóa bảng' : action === 'insert' ? 'Đề xuất thêm bảng' : `Đề xuất sửa bảng${changes ? ` (${changes})` : ''}`
      } else {
        const parts: DiffPart[] =
          action === 'delete' ? [{ type: 'del', text: block.text }] : action === 'insert' ? [{ type: 'ins', text: block.proposal.text }] : diffWords(block.text, block.proposal.text)
        shown = (
          <p className="cv-diff">
            {parts.map((part, index) =>
              part.type === 'same' ? <span key={index}>{part.text}</span> : part.type === 'del' ? <del key={index}>{part.text}</del> : <ins key={index}>{part.text}</ins>,
            )}
          </p>
        )
        lead = action === 'delete' ? 'Đề xuất xóa đoạn' : action === 'insert' ? 'Đề xuất thêm đoạn' : 'Đề xuất của trợ lý'
      }
      return (
        <div key={block.id} className={`cv-block cv-block--${block.kind} cv-block--proposal`} {...(isTable ? { 'data-table-id': block.id } : { 'data-block-id': block.id })}>
          {shown}
          <div className="cv-proposal cv-ui">
            <span className="cv-proposal__note"><Icon name="canvas" size={16} />{lead}{note ? ` · ${note}` : ''}</span>
            {block.proposal.checks && block.proposal.checks.length > 0 && (
              <ul className="cv-proposal__checks">
                {block.proposal.checks.map((item, index) => (
                  <li key={index} className={item.severity === 'warning' ? 'cv-proposal__check cv-proposal__check--warn' : 'cv-proposal__check'}>
                    <Icon name={item.severity === 'warning' ? 'alert' : 'info'} size={14} />
                    {item.message}
                  </li>
                ))}
              </ul>
            )}
            <span className="cv-proposal__btns">
              <Button variant="primary" icon="check" loading={busy} disabled={locked} onClick={() => void run(() => onAccept(block.id))}>Chấp nhận</Button>
              <Button icon="close" disabled={busy || locked} onClick={() => void run(() => onReject(block.id))}>Từ chối</Button>
            </span>
          </div>
        </div>
      )
    }
    const editable = !locked
    const open = () => {
      // Dragging to select text also ends in a click: only a plain click starts editing.
      if (editable && !window.getSelection()?.toString()) setEditing(target)
    }
    const owner = block.owner === 'assistant' ? 'cv-f cv-f--assistant' : 'cv-f cv-f--user'
    if (block.kind === 'table' && block.table) {
      // No data-block-id: the quick requests on selected text (rewrite, shorten) are for prose.
      return (
        <div key={block.id} className={`cv-block cv-block--table${block.owner === 'assistant' ? ' cv-block--by-assistant' : ''}`} data-table-id={block.id}>
          <TableEditor
            spec={block.table}
            editable={editable}
            onChange={(table) => onEditTable(block.id, table)}
            problems={block.problems}
            tooWide={block.too_wide && !block.landscape}
            tools={
              <>
                <IconButton icon="plus" size={16} label="Thêm đoạn bên dưới" onClick={() => startInsert(block.id)} />
                <IconButton icon="trash" size={16} label="Xóa bảng" danger disabled={busy} onClick={() => void run(() => onDeleteBlock(block.id))} />
              </>
            }
          />
        </div>
      )
    }
    if (block.kind === 'appendix') {
      return (
        <div key={block.id} className="cv-block cv-block--appendix" data-block-id={block.id}>
          <div className="cv-appx__break cv-ui">
            <span>Phụ lục in từ trang mới</span>
            {block.landscape && <Chip tone="info" icon="landscape">Khổ ngang</Chip>}
          </div>
          <p className="cv-appx__label">{block.label ?? 'Phụ lục'}</p>
          <p
            className={editable ? 'cv-appx__title cv-text--editable' : 'cv-appx__title'}
            {...(editable ? { tabIndex: 0, 'aria-label': 'Tên phụ lục, nhấn Enter để sửa', onClick: open, onKeyDown: (event: KeyboardEvent) => {
              if (event.key === 'Enter') {
                event.preventDefault()
                setEditing(target)
              }
            } } : {})}
          >
            <span className={owner}>{block.text}</span>
          </p>
          <p className="cv-appx__ref">{attachedTo(draft)}</p>
          {editable && (
            <span className="cv-block__tools cv-ui">
              <IconButton icon="edit" size={16} label="Sửa tên phụ lục" onClick={() => setEditing(target)} />
              <IconButton icon="plus" size={16} label="Thêm đoạn bên dưới" onClick={() => startInsert(block.id)} />
              <IconButton icon="trash" size={16} label="Xóa phụ lục" onClick={() => void run(() => onDeleteBlock(block.id))} />
            </span>
          )}
        </div>
      )
    }
    const stale = block.stale ? (
      <div className="cv-stale cv-ui" role="status">
        <Icon name="alert" size={14} />
        <span>
          Số liệu trong bảng đã đổi{block.stale.figures.length ? ` (${block.stale.figures.join(', ')} không còn trong bảng)` : ''}: đoạn này cần xem lại.
        </span>
        {editable && <Button size="sm" variant="ghost" icon="check" loading={busy} onClick={() => void run(() => onReviewed(block.id))}>Đã xem</Button>}
      </div>
    ) : null
    return (
      <div key={block.id} className={`cv-block cv-block--${block.kind}`} data-block-id={block.id}>
        <p
          className={editable ? 'cv-text cv-text--editable' : 'cv-text'}
          {...(editable
            ? {
                tabIndex: 0,
                'aria-label': 'Đoạn nội dung, nhấn Enter để sửa',
                onClick: open,
                onKeyDown: (event: KeyboardEvent) => {
                  if (event.key === 'Enter' && event.target === event.currentTarget) {
                    event.preventDefault()
                    setEditing(target)
                  }
                },
              }
            : {})}
        >
          <span className={owner}>
            <Lines text={block.text} />
          </span>
        </p>
        {stale}
        {editable && (
          <span className="cv-block__tools cv-ui">
            <IconButton icon="edit" size={16} label="Sửa đoạn" onClick={() => setEditing(target)} />
            <IconButton icon="plus" size={16} label="Thêm đoạn bên dưới" onClick={() => startInsert(block.id)} />
            <IconButton icon="trash" size={16} label="Xóa đoạn" onClick={() => void run(() => onDeleteBlock(block.id))} />
          </span>
        )}
      </div>
    )
  }

  const startInsert = (after: string | null) => {
    setEditing(null)
    setInserting({ after, text: '', attempt: 0 })
  }
  const commitInsert = async (text: string) => {
    const current = inserting
    if (!current) return
    const trimmed = text.trim()
    if (!trimmed) {
      setInserting(null)
      return
    }
    // On failure the editor stays open with the text (the error is shown above the page).
    const next = await onInsertBlock(current.after, trimmed)
    setInserting(next ? null : { ...current, text: trimmed, attempt: current.attempt + 1 })
  }
  const insertEditor = (after: string | null): ReactNode =>
    inserting && inserting.after === after ? (
      <div key={`new-${after ?? 'start'}`} className="cv-block cv-block--para">
        <InlineEditor key={inserting.attempt} value={inserting.text} label="Đoạn mới" onCommit={(text) => void commitInsert(text)} onCancel={() => setInserting(null)} />
      </div>
    ) : null

  // Blocks from the first appendix on print after the signature.
  const split = draft.blocks.findIndex((block) => block.kind === 'appendix')
  const body = split < 0 ? draft.blocks : draft.blocks.slice(0, split)
  const appendices = split < 0 ? [] : draft.blocks.slice(split)
  const last = body[body.length - 1]

  return (
    <article
      className="cv-page"
      aria-label="Bản dự thảo"
      ref={(element) => {
        pageRef.current = element
        scrollRef.current = element?.closest<HTMLElement>('.cv-scroll') ?? null
      }}
    >
      <header className="cv-head">
        <div className="cv-head__left">
          {fields.co_quan_chu_quan && <div className="cv-head__org">{field('co_quan_chu_quan')}</div>}
          {fields.co_quan_ban_hanh && <div className="cv-head__issuer">{field('co_quan_ban_hanh')}</div>}
          {fields.so_ky_hieu && <div className="cv-head__number">{field('so_ky_hieu')}</div>}
          {fields.so_ky_hieu && <div className="cv-head__note">Văn thư cấp số khi ban hành</div>}
        </div>
        <div className="cv-head__right">
          {fields.quoc_hieu && <div className="cv-head__nation">{field('quoc_hieu')}</div>}
          {fields.tieu_ngu && <div className="cv-head__motto">{field('tieu_ngu')}</div>}
          {fields.dia_danh_ngay && <div className="cv-head__date">{field('dia_danh_ngay')}</div>}
        </div>
      </header>

      {fields.ten_loai && <h3 className="cv-title">{field('ten_loai')}</h3>}
      {fields.trich_yeu && <p className={fields.ten_loai ? 'cv-subject cv-subject--title' : 'cv-subject'}>{field('trich_yeu')}</p>}
      {fields.kinh_gui && <p className="cv-to">{field('kinh_gui')}</p>}
      {fields.can_cu && <div className="cv-basis">{field('can_cu')}</div>}

      <div className="cv-body">
        {body.length === 0 && <p className="cv-body__empty">Phần nội dung chưa có. Trợ lý đang soạn hoặc bạn có thể tự thêm đoạn.</p>}
        {body.length === 0 && insertEditor(null)}
        {body.map((block) => (
          <Fragment key={block.id}>
            {blockView(block)}
            {insertEditor(block.id)}
          </Fragment>
        ))}
        {!locked && !inserting && (
          <button type="button" className="cv-add cv-ui" onClick={() => startInsert(last?.id ?? null)}>
            <Icon name="plus" size={16} />
            Thêm đoạn
          </button>
        )}
      </div>

      <footer className="cv-foot">
        <div className="cv-foot__to">
          {fields.noi_nhan && (
            <>
              <b><i>Nơi nhận:</i></b>
              <div>{field('noi_nhan')}</div>
            </>
          )}
        </div>
        <div className="cv-foot__sign">
          {fields.quyen_han && <div className="cv-foot__power">{field('quyen_han')}</div>}
          <div className="cv-foot__space" />
          {fields.nguoi_ky && <div className="cv-foot__signer">{field('nguoi_ky')}</div>}
        </div>
      </footer>

      {appendices.length > 0 && (
        <section className="cv-appendices" aria-label="Phụ lục">
          {appendices.map((block) => (
            <Fragment key={block.id}>
              {blockView(block)}
              {insertEditor(block.id)}
            </Fragment>
          ))}
        </section>
      )}

      {selection && createPortal(
        <SelectionToolbar
          info={selection}
          disabled={locked}
          onAsk={(action: AskAction) => {
            onAsk(ASK_PROMPTS[action], { block_id: selection.blockId, selection: selection.text, action })
            window.getSelection()?.removeAllRanges()
            clearSelection()
          }}
        />,
        document.body,
      )}
    </article>
  )
}
