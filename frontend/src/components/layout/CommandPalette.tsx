import { createContext, useCallback, useContext, useEffect, useId, useMemo, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useNavigate } from 'react-router-dom'
import { request, type DocumentPage, type DocumentSummary } from '../../api'
import { useAuth } from '../../auth/AuthContext'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { useLayer } from '../../hooks/useLayer'
import { useTheme } from '../../hooks/useTheme'
import { documentSymbol, documentTitle } from '../../lib/documents'
import { formatDate } from '../../lib/format'
import { readStorage, writeStorage } from '../../lib/storage'
import { StateChip } from '../Chip'
import { Icon, docTypeIcon, type IconName } from '../Icon'
import { Spinner } from '../Spinner'
import { NAV, canSee } from './nav'

interface PaletteApi {
  open: () => void
  close: () => void
}

const PaletteContext = createContext<PaletteApi | null>(null)

/** Opens the command palette from anywhere inside the shell. */
export function useCommandPalette(): PaletteApi {
  const value = useContext(PaletteContext)
  if (!value) throw new Error('useCommandPalette must be used inside CommandPaletteProvider')
  return value
}

interface Entry {
  key: string
  group: 'recent' | 'nav' | 'action' | 'doc'
  label: string
  meta?: string
  icon: IconName
  /** Route to open. */
  to?: string
  /** Router state passed with `to` (the Kho page reads `{ action: 'upload' }`). */
  state?: unknown
  /** Or run something instead. */
  run?: () => void
  /** Matching words besides the label. */
  keywords?: string[]
  /** Remember in "Gần đây" (pages and documents; not toggles). */
  remember?: boolean
  doc?: DocumentSummary
}

interface Recent {
  key: string
  label: string
  meta?: string
  icon: IconName
  to: string
  state?: unknown
}

const RECENT_KEY = 'qk3.recent'
const GROUP_LABELS: Record<Entry['group'], string> = { recent: 'Gần đây', nav: 'Điều hướng', action: 'Hành động', doc: 'Văn bản' }

function loadRecent(): Recent[] {
  try {
    const parsed: unknown = JSON.parse(readStorage('session', RECENT_KEY) ?? '[]')
    return Array.isArray(parsed) ? (parsed as Recent[]).filter((item) => item && typeof item.to === 'string' && typeof item.label === 'string').slice(0, 5) : []
  } catch {
    return []
  }
}

function remember(entry: Recent): void {
  const next = [entry, ...loadRecent().filter((item) => item.key !== entry.key)].slice(0, 5)
  writeStorage('session', RECENT_KEY, JSON.stringify(next))
}

/** Lower-case and strip Vietnamese diacritics one character at a time, so indexes still line up with the original text. */
function fold(text: string): string {
  return Array.from(text.toLowerCase(), (char) => (char === 'đ' ? 'd' : char.normalize('NFD').replace(/[̀-ͯ]/g, ''))).join('')
}

function Highlight({ text, query }: { text: string; query: string }) {
  const needle = fold(query.trim())
  const at = needle ? fold(text).indexOf(needle) : -1
  if (at < 0) return <>{text}</>
  return (
    <>
      {text.slice(0, at)}
      <mark className="palette__mark">{text.slice(at, at + needle.length)}</mark>
      {text.slice(at + needle.length)}
    </>
  )
}

function matches(entry: Pick<Entry, 'label' | 'keywords'>, query: string): boolean {
  const needle = fold(query.trim())
  if (!needle) return true
  return [entry.label, ...(entry.keywords ?? [])].some((text) => fold(text).includes(needle))
}

/** Shell-wide Ctrl+K palette: pages, quick actions and a debounced document search. */
export function CommandPaletteProvider({ children }: { children: ReactNode }) {
  const [isOpen, setOpen] = useState(false)
  const open = useCallback(() => setOpen(true), [])
  const close = useCallback(() => setOpen(false), [])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      const typing = !!target && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName))
      if ((event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setOpen((value) => !value)
      } else if (event.key === '/' && !typing && !event.ctrlKey && !event.metaKey && !event.altKey) {
        event.preventDefault()
        setOpen(true)
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  const value = useMemo(() => ({ open, close }), [open, close])
  return (
    <PaletteContext.Provider value={value}>
      {children}
      {isOpen && <Palette onClose={close} />}
    </PaletteContext.Provider>
  )
}

type DocSearch = { status: 'idle' | 'loading' | 'done' | 'error'; items: DocumentSummary[] }

function Palette({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate()
  const { user } = useAuth()
  const { theme, toggle } = useTheme()
  const listId = useId()
  const panelRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const [docs, setDocs] = useState<DocSearch>({ status: 'idle', items: [] })
  const [recents] = useState(loadRecent)
  useLayer(panelRef, { onClose })

  const debounced = useDebouncedValue(query.trim(), 220)
  useEffect(() => {
    if (debounced.length < 2) {
      setDocs({ status: 'idle', items: [] })
      return
    }
    const controller = new AbortController()
    setDocs((current) => ({ ...current, status: 'loading' }))
    request<DocumentPage>('/api/documents', { query: { q: debounced, limit: 6 }, signal: controller.signal })
      .then((page) => setDocs({ status: 'done', items: page.items }))
      .catch(() => {
        if (!controller.signal.aborted) setDocs({ status: 'error', items: [] })
      })
    return () => controller.abort()
  }, [debounced])

  const entries = useMemo<Entry[]>(() => {
    const nav: Entry[] = NAV.filter((item) => canSee(item, user?.role)).map((item) => ({
      key: `nav-${item.to}`, group: 'nav', label: item.label, icon: item.icon, to: item.to, keywords: item.keywords, remember: true, meta: item.description,
    }))
    const actions: Entry[] = [
      { key: 'act-ask', group: 'action', label: 'Hỏi trợ lý AI', meta: 'Đặt câu hỏi về văn bản', icon: 'sparkles', to: '/tro-ly', keywords: ['hỏi', 'câu hỏi', 'trợ lý', 'tóm tắt'] },
      { key: 'act-upload', group: 'action', label: 'Tải văn bản lên', meta: 'Thêm vào kho văn bản', icon: 'upload', to: '/kho', state: { action: 'upload' }, keywords: ['upload', 'thêm', 'nhập'] },
      { key: 'act-check', group: 'action', label: 'Kiểm tra thể thức một tệp', meta: 'Đối chiếu thể thức quy định', icon: 'fileCheck', to: '/kiem-tra', keywords: ['thể thức', 'định dạng', 'lỗi'] },
      { key: 'act-spell', group: 'action', label: 'Kiểm tra chính tả', meta: 'Văn bản dán hoặc một tệp', icon: 'spellcheck', to: '/chinh-ta', keywords: ['chính tả', 'sai dấu', 'soát lỗi'] },
      { key: 'act-theme', group: 'action', label: theme === 'dark' ? 'Đổi sang giao diện sáng' : 'Đổi sang giao diện tối', meta: 'Giao diện', icon: theme === 'dark' ? 'sun' : 'moon', run: toggle, keywords: ['sáng', 'tối', 'dark', 'light', 'giao diện', 'theme'] },
    ]
    const found: Entry[] = docs.items.map((doc) => ({
      key: `doc-${doc.id}`,
      group: 'doc',
      label: documentTitle(doc),
      meta: [documentSymbol(doc), doc.unit_name || doc.unit_id, doc.issued_date ? formatDate(doc.issued_date) : ''].filter(Boolean).join(' · '),
      icon: docTypeIcon(doc.document_type, doc.level === 'mat'),
      to: `/kho/${doc.id}`,
      remember: true,
      doc,
    }))
    const recent: Entry[] = recents.map((item) => ({ key: `recent-${item.key}`, group: 'recent', label: item.label, meta: item.meta, icon: item.icon, to: item.to, state: item.state }))
    const q = query.trim()
    if (!q) return [...recent, ...nav, ...actions]
    return [...nav.filter((entry) => matches(entry, q)), ...actions.filter((entry) => matches(entry, q)), ...found]
  }, [docs.items, query, recents, theme, toggle, user?.role])

  useEffect(() => setActive(0), [query, docs.items])
  useEffect(() => {
    listRef.current?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: 'nearest' })
  }, [active, entries])

  const run = (entry: Entry) => {
    if (entry.remember && entry.to) {
      remember({ key: entry.key.replace(/^recent-/, ''), label: entry.label, meta: entry.meta, icon: entry.icon, to: entry.to, state: entry.state })
    }
    onClose()
    if (entry.run) entry.run()
    else if (entry.to) navigate(entry.to, { state: entry.state })
  }

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      if (entries.length) setActive((index) => (index + 1) % entries.length)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      if (entries.length) setActive((index) => (index - 1 + entries.length) % entries.length)
    } else if (event.key === 'Enter') {
      event.preventDefault()
      const entry = entries[active]
      if (entry) run(entry)
    }
  }

  const searching = query.trim().length >= 2
  const nothing = searching && entries.length === 0 && docs.status !== 'loading'
  let lastGroup: Entry['group'] | null = null

  return createPortal(
    <div className="layer-backdrop palette-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div ref={panelRef} className="palette" role="dialog" aria-modal="true" aria-label="Tìm kiếm và lệnh nhanh" tabIndex={-1} onKeyDown={onKeyDown}>
        <div className="palette__input">
          <Icon name="search" size={20} />
          <input
            data-autofocus
            type="text"
            role="combobox"
            aria-expanded="true"
            aria-controls={listId}
            aria-activedescendant={entries[active] ? `${listId}-${active}` : undefined}
            aria-autocomplete="list"
            aria-label="Tìm văn bản, trang hoặc lệnh"
            placeholder="Tìm văn bản, lệnh…"
            autoComplete="off"
            spellCheck={false}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <kbd aria-hidden="true">Esc</kbd>
        </div>
        <div className="palette__list" id={listId} role="listbox" aria-label="Kết quả" ref={listRef}>
          {entries.map((entry, index) => {
            const heading = entry.group !== lastGroup
            lastGroup = entry.group
            return (
              <div key={entry.key} role="presentation">
                {heading && <div className="palette__group" role="presentation">{GROUP_LABELS[entry.group]}</div>}
                <div
                  id={`${listId}-${index}`}
                  role="option"
                  aria-selected={index === active}
                  className="palette__item"
                  onMouseMove={() => active !== index && setActive(index)}
                  onClick={() => run(entry)}
                >
                  <span className="palette__item-icon"><Icon name={entry.icon} size={18} /></span>
                  <span className="palette__item-text">
                    <span className="palette__item-title"><Highlight text={entry.label} query={entry.group === 'recent' ? '' : query} /></span>
                    {entry.meta && <span className="palette__item-meta">{entry.meta}</span>}
                  </span>
                  <span className="palette__item-end">
                    {entry.doc ? <StateChip state={entry.doc.state} /> : index === active ? <><kbd aria-hidden="true">↵</kbd></> : null}
                  </span>
                </div>
              </div>
            )
          })}
          {searching && docs.status === 'loading' && (
            <div className="palette__status" role="status"><Spinner size={14} />Đang tìm văn bản…</div>
          )}
          {searching && docs.status === 'error' && <div className="palette__status" role="status"><Icon name="alertCircle" size={16} />Không tìm được văn bản. Kiểm tra kết nối rồi thử lại.</div>}
          {nothing && (
            <div className="palette__empty">
              <strong>Không có kết quả cho “{query.trim()}”</strong>
              <span>Thử số ký hiệu, trích yếu hoặc tên đơn vị.</span>
            </div>
          )}
        </div>
        <div className="palette__foot" aria-hidden="true">
          <span><kbd>↑</kbd><kbd>↓</kbd> chọn</span>
          <span><kbd>↵</kbd> mở</span>
          <span><kbd>Esc</kbd> đóng</span>
        </div>
      </div>
    </div>,
    document.body,
  )
}
