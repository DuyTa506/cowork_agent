import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { chatApi } from '../../api'
import type { ChatDraft, DraftCheck, DraftPatch, DraftStyle, SelectionContext } from '../../api/chat'
import { useElementWidth } from '../../hooks/useMediaQuery'
import { saveBlob } from '../../lib/download'
import { formatTime } from '../../lib/format'
import { Alert } from '../Alert'
import { Button } from '../Button'
import { Chip } from '../Chip'
import { ConfirmDialog } from '../ConfirmDialog'
import { Icon } from '../Icon'
import { IconButton } from '../IconButton'
import { PopMenu } from '../assistant/PopMenu'
import { Tabs, tabPanelProps } from '../Tabs'
import { useToast } from '../Toast'
import { CheckPanel, problemCount } from './CheckResult'
import { DraftPage } from './DraftPage'
import { HistoryPanel } from './HistoryPanel'
import { SaveDraftDialog } from './SaveDraftDialog'

interface CanvasPanelProps {
  sessionId: string
  draft: ChatDraft
  /** The assistant is answering: edits to the page are paused. */
  running: boolean
  onDraft: (draft: ChatDraft | null) => void
  /** Closes the Canvas (the draft stays in the conversation). */
  onClose: () => void
  /** Sends a request about a selected passage to the assistant. */
  onAsk: (prompt: string, context: SelectionContext) => void
}

type View = 'page' | 'check' | 'history'

/** A4 width in CSS pixels; the page is drawn at this width and scaled down to fit the panel. */
const PAGE_WIDTH = 794
/** From this panel width the check result and the history sit beside the page instead of in tabs. */
const WIDE = 1060

const messageOf = (error: unknown, fallback: string) => (error instanceof Error && error.message ? error.message : fallback)

/**
 * Drafting canvas: toolbar (template, TT68, version, format check, save, export), the draft as a paper page scaled to fit,
 * and the format check and history as tabs (beside the page when there is room).
 */
export function CanvasPanel({ sessionId, draft, running, onDraft, onClose, onAsk }: CanvasPanelProps) {
  const notify = useToast()
  const [error, setError] = useState<string | null>(null)
  const [check, setCheck] = useState<{ result: DraftCheck; version: number } | null>(null)
  const [checking, setChecking] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [saveOpen, setSaveOpen] = useState(false)
  const [saved, setSaved] = useState<{ id: number; title: string } | null>(null)
  const [discardOpen, setDiscardOpen] = useState(false)
  const [view, setView] = useState<View>('page')
  const [measure, width] = useElementWidth<HTMLDivElement>()
  const wide = width >= WIDE

  const apply = async (action: () => Promise<ChatDraft>): Promise<ChatDraft | null> => {
    setError(null)
    try {
      const next = await action()
      onDraft(next)
      return next
    } catch (failure) {
      setError(messageOf(failure, 'Không cập nhật được bản dự thảo.'))
      return null
    }
  }
  const patch = (change: DraftPatch) => apply(() => chatApi.patchDraft(sessionId, change))

  const runCheck = async () => {
    setChecking(true)
    setError(null)
    try {
      setCheck({ result: await chatApi.checkDraft(sessionId), version: draft.version })
      setView((current) => (current === 'history' ? current : 'check'))
    } catch (failure) {
      setError(messageOf(failure, 'Không kiểm tra được thể thức.'))
    } finally {
      setChecking(false)
    }
  }

  const exportDocx = async () => {
    setExporting(true)
    setError(null)
    try {
      saveBlob(await chatApi.exportDraft(sessionId), `${draft.title || 'du-thao'}.docx`)
    } catch (failure) {
      setError(messageOf(failure, 'Không xuất được tệp DOCX.'))
    } finally {
      setExporting(false)
    }
  }

  const pickStyle = async (next: DraftStyle) => {
    const saved = await patch({ style: next })
    if (!saved) return
    const preset = nameOf(saved.style_options?.presets, saved.style?.preset, 'Chuẩn đơn vị')
    const detail = nameOf(saved.style_options?.detail, saved.style?.detail, 'Vừa')
    if (saved.blocks.length === 0) {
      notify(`Đã chọn văn phong ${preset}, mức ${detail}.`, 'info')
      return
    }
    notify(`Đã chọn văn phong ${preset}, mức ${detail}.`, 'info', {
      duration: 8000,
      action: {
        label: 'Áp dụng cho toàn văn',
        onClick: () => onAsk(
          `Áp dụng văn phong "${preset}", mức chi tiết "${detail}" cho toàn bộ nội dung đã viết. Đọc canvas_read, rồi đề xuất sửa từng đoạn bằng canvas_edit_block (replace). Giữ nguyên số liệu, tên riêng, ngày tháng và các mục bắt buộc của loại văn bản. Không dùng canvas_set_content.`,
          { block_id: '', selection: '', action: 'restyle' },
        ),
      },
    })
  }

  const problems = check ? problemCount(check.result) : 0
  // "Đạt" only when nothing is left to fix and nothing is left to fill in.
  const verdict = problems > 0 ? { ok: false, label: String(problems) } : draft.missing.length > 0 ? { ok: false, label: 'Chưa đủ' } : { ok: true, label: 'Đạt' }
  const stale = check !== null && check.version !== draft.version

  /** Scrolls to a missing field and opens it for typing. */
  const goToField = (key: string) => {
    setView('page')
    window.requestAnimationFrame(() => {
      const target = document.querySelector<HTMLElement>(`.cv-page [data-field="${key}"]`)
      target?.scrollIntoView({ block: 'center', behavior: 'smooth' })
      target?.click()
    })
  }

  const checkLabel = (
    <>
      Kiểm tra thể thức
      {check && (
        <span className={verdict.ok ? 'cv-pill cv-pill--ok' : 'cv-pill cv-pill--warn'}>
          <Icon name={verdict.ok ? 'check' : 'alert'} size={13} />
          {verdict.label}
        </span>
      )}
    </>
  )

  const items: { key: View; label: string; count?: ReactNode }[] = [
    ...(wide ? [] : [{ key: 'page' as const, label: 'Bản dự thảo' }]),
    { key: 'check', label: 'Kiểm tra thể thức', count: check ? verdict.label : undefined },
    { key: 'history', label: 'Lịch sử', count: draft.history.length || undefined },
  ]
  const current: View = wide && view === 'page' ? 'check' : view

  const paper = (
    <Paper
      draft={draft}
      running={running}
      error={error}
      saved={saved}
      onGoToField={goToField}
      onDraftPatch={patch}
      apply={apply}
      sessionId={sessionId}
      onAsk={onAsk}
    />
  )
  const inspector = current === 'history' ? <HistoryPanel draft={draft} /> : <CheckPanel check={check?.result ?? null} stale={stale} checking={checking} missing={draft.missing.length} onRun={() => void runCheck()} />

  return (
    <div className="canvas" ref={measure} data-wide={wide ? 'yes' : 'no'}>
      <header className="cv-bar">
        <div className="cv-bar__top">
          <div className="cv-bar__id">
            <Icon name="canvas" size={20} className="cv-bar__icon" />
            <h2 className="cv-bar__name">{draft.template.name}</h2>
            <Chip tone="blue" icon="shield">TT68</Chip>
            <StyleControls draft={draft} disabled={running} onPick={(next) => void pickStyle(next)} />
            <span className="cv-bar__ver tnum">Phiên bản {draft.version}<span className="cv-bar__saved"> · Đã lưu {formatTime(draft.updated_at)}</span></span>
          </div>
          <div className="cv-bar__tools">
            <PopMenu
              label="Thêm thao tác với bản dự thảo"
              items={[{ key: 'discard', label: 'Bỏ bản dự thảo', icon: 'trash', danger: true, onSelect: () => setDiscardOpen(true) }]}
              trigger={(props) => (
                <button {...props} type="button" className="icon-btn cv-bar__btn" aria-label="Thêm thao tác" title="Thêm thao tác">
                  <Icon name="more" size={20} />
                </button>
              )}
            />
            <IconButton className="cv-bar__btn" icon="close" size={20} label="Đóng Canvas" onClick={onClose} />
          </div>
        </div>
        <div className="cv-bar__actions">
          <Button icon="shield" onClick={() => void runCheck()} loading={checking}>{checkLabel}</Button>
          <Button icon="save" onClick={() => setSaveOpen(true)}>Lưu vào kho</Button>
          <Button variant="primary" icon="download" onClick={() => void exportDocx()} loading={exporting}>Xuất DOCX</Button>
        </div>
      </header>
      <div className="cv-legend" aria-label="Chú giải">
        <span><i className="cv-key cv-key--system">Gạch chấm</i> hệ thống tự điền</span>
        <span><i className="cv-key cv-key--assistant">Nền vàng nhạt</i> trợ lý soạn</span>
        <span><i className="cv-key cv-key--user">Gạch đứt</i> đồng chí nhập</span>
      </div>
      {wide ? (
        <div className="cv-split">
          <div className="cv-main">{paper}</div>
          <aside className="cv-side" aria-label="Kiểm tra và lịch sử">
            <Tabs items={items} value={current} onChange={setView} label="Kiểm tra và lịch sử" idPrefix="cvs" />
            <div className="cv-side__body" {...tabPanelProps('cvs', current)}>{inspector}</div>
          </aside>
        </div>
      ) : (
        <>
          <Tabs items={items} value={current} onChange={setView} label="Các phần của Canvas" idPrefix="cvs" />
          <div className="cv-single">
            <div className="cv-pane" hidden={current !== 'page'} {...(current === 'page' ? tabPanelProps('cvs', 'page') : {})}>{paper}</div>
            {current !== 'page' && <div className="cv-side__body" {...tabPanelProps('cvs', current)}>{inspector}</div>}
          </div>
        </>
      )}
      {saveOpen && (
        <SaveDraftDialog
          sessionId={sessionId}
          title={draft.title}
          onClose={() => setSaveOpen(false)}
          onSaved={(document) => {
            setSaveOpen(false)
            setSaved({ id: document.id, title: document.title || draft.title })
            notify('Đã lưu bản dự thảo vào Kho văn bản.')
          }}
        />
      )}
      {discardOpen && (
        <ConfirmDialog
          title="Bỏ bản dự thảo"
          confirmLabel="Bỏ bản dự thảo"
          danger
          onCancel={() => setDiscardOpen(false)}
          onConfirm={async () => {
            await chatApi.deleteDraft(sessionId)
            setDiscardOpen(false)
            onDraft(null)
          }}
        >
          <p>Bỏ bản dự thảo của cuộc trò chuyện này? Nội dung và lịch sử chỉnh sửa sẽ bị xóa. Nếu cần, hãy lưu vào kho hoặc xuất DOCX trước.</p>
        </ConfirmDialog>
      )}
    </div>
  )
}

interface PaperProps {
  draft: ChatDraft
  running: boolean
  error: string | null
  saved: { id: number; title: string } | null
  sessionId: string
  onGoToField: (key: string) => void
  onDraftPatch: (change: DraftPatch) => Promise<ChatDraft | null>
  apply: (action: () => Promise<ChatDraft>) => Promise<ChatDraft | null>
  onAsk: CanvasPanelProps['onAsk']
}

/** The scrolling area with notices and the paper sheet, drawn at A4 width and scaled to the space available. */
function Paper({ draft, running, error, saved, sessionId, onGoToField, onDraftPatch, apply, onAsk }: PaperProps) {
  const [measure, width] = useElementWidth<HTMLDivElement>()
  const sheetRef = useRef<HTMLDivElement>(null)
  const [height, setHeight] = useState(0)
  const scale = width > 0 ? Math.min(1, Math.max(0.4, (width - 32) / PAGE_WIDTH)) : 1

  const watch = useCallback((element: HTMLDivElement | null) => {
    sheetRef.current = element
  }, [])
  useEffect(() => {
    const element = sheetRef.current
    if (!element) return
    const observer = new ResizeObserver(() => setHeight(element.offsetHeight))
    observer.observe(element)
    setHeight(element.offsetHeight)
    return () => observer.disconnect()
  }, [])

  const missing = draft.missing.map((key) => ({ key, label: draft.fields[key]?.label ?? key }))

  return (
    <div className="cv-scroll" ref={measure}>
      <div className="cv-notices" style={{ width: PAGE_WIDTH * scale }}>
        {error && <Alert kind="error">{error}</Alert>}
        {saved && (
          <Alert kind="success" action={<Link className="btn" to={`/kho/${saved.id}`}>Mở trong kho</Link>}>
            Đã lưu “{saved.title}” vào Kho văn bản.
          </Alert>
        )}
        {missing.length > 0 && (
          <div className="cv-missing" role="status">
            <span className="cv-missing__lead"><Icon name="alert" size={16} />Còn thiếu {missing.length} mục</span>
            <ul>
              {missing.map((item) => (
                <li key={item.key}>
                  <button type="button" onClick={() => onGoToField(item.key)}>{item.label}</button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
      <div className="cv-fit" style={{ width: PAGE_WIDTH * scale, height: height * scale }}>
        <div className="cv-sheet" ref={watch} style={{ width: PAGE_WIDTH, transform: `scale(${scale})`, ['--cv-scale' as string]: scale }}>
          <DraftPage
            draft={draft}
            locked={running}
            onEditField={async (key, text) => void (await onDraftPatch({ fields: { [key]: text } }))}
            onEditBlock={async (id, text) => void (await onDraftPatch({ blocks: [{ id, text }] }))}
            onEditTable={async (id, table) => void (await onDraftPatch({ blocks: [{ id, table }] }))}
            onReviewed={async (id) => void (await onDraftPatch({ reviewed: [id] }))}
            onDeleteBlock={async (id) => void (await onDraftPatch({ delete: [id] }))}
            onInsertBlock={(after, text) => onDraftPatch({ insert: { after, kind: 'para', text } })}
            onAccept={async (id) => void (await apply(() => chatApi.acceptProposal(sessionId, id)))}
            onReject={async (id) => void (await apply(() => chatApi.rejectProposal(sessionId, id)))}
            onAsk={onAsk}
          />
        </div>
      </div>
    </div>
  )
}

const nameOf = (items: { id: string; name: string }[] | undefined, id: string | undefined, fallback: string) =>
  items?.find((item) => item.id === id)?.name ?? fallback

/** Preset menu and the short / medium / full detail switch, beside the TT68 chip. */
function StyleControls({ draft, disabled, onPick }: { draft: ChatDraft; disabled: boolean; onPick: (style: DraftStyle) => void }) {
  const options = draft.style_options
  const current: DraftStyle = draft.style ?? { preset: 'don_vi', detail: 'vua' }
  if (!options) return null
  return (
    <div className="cv-style">
      <PopMenu
        label="Chọn văn phong"
        align="start"
        width={220}
        items={options.presets.map((item) => ({
          key: item.id,
          label: item.name,
          checked: item.id === current.preset,
          disabled,
          onSelect: () => { if (item.id !== current.preset) onPick({ preset: item.id, detail: current.detail }) },
        }))}
        trigger={(props) => (
          <button {...props} type="button" className="cv-style__preset" disabled={disabled}>
            Văn phong: {nameOf(options.presets, current.preset, 'Chuẩn đơn vị')}
            <Icon name="chevronDown" size={14} />
          </button>
        )}
      />
      <div className="seg" role="radiogroup" aria-label="Mức độ chi tiết">
        {options.detail.map((item) => (
          <button
            key={item.id}
            type="button"
            role="radio"
            aria-checked={item.id === current.detail}
            className={item.id === current.detail ? 'seg__item seg__item--on' : 'seg__item'}
            disabled={disabled}
            onClick={() => { if (item.id !== current.detail) onPick({ preset: current.preset, detail: item.id }) }}
          >
            {item.name}
          </button>
        ))}
      </div>
    </div>
  )
}
