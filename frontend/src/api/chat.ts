import { fetchCurrentUser } from './auth'
import { ApiError, request, requestBlob, uploadForm, type RequestOptions } from './client'
import { clearToken, getToken } from '../auth/tokenStorage'
import type { DocumentSummary, Paragraph } from './types'

/**
 * Trợ lý AI: chat sessions, attachments and the Canvas draft (contract: docs/CHAT_API.md).
 * With `VITE_MOCK_CHAT=1` every call is answered by `src/dev/mockChat.ts` (loaded lazily, never in a production build).
 */

/* ---------- types ---------- */

export interface ChatSession {
  /** Opaque text id (a hex string), not a number. */
  id: string
  title: string
  created_at: string
  updated_at: string
}

export type StepStatus = 'running' | 'done' | 'error'

/** A document (or attachment) a tool step looked at; `doc_id` is "att<N>" for chat attachments. */
export interface StepDocumentRef {
  doc_id: number | string
  label: string
  section: string
}

export interface StepDetail {
  /** Full reasoning of a `thinking` step. */
  text?: string
  arguments?: Record<string, unknown>
  result?: { documents?: StepDocumentRef[]; count?: number; error?: string }
}

/** One "việc đã làm" row; steps arrive repeatedly and are merged by `id`. */
export interface ChatStep {
  id: string | number
  kind: 'thinking' | 'tool'
  title: string
  summary: string
  status: StepStatus
  duration_ms: number
  tool: string | null
  detail: StepDetail | null
}

export interface Citation {
  n: number
  doc_id: number | string
  kind: 'store' | 'attachment'
  title: string
  /** Document number and symbol, for example "24/KH-PTM". */
  ref: string
  doc_type: string
  date: string
  unit_name: string
  section: string
  text: string
  /** Paragraph range to highlight in the viewer; [-1, -1] when unknown. */
  pi: [number, number]
  /** False when the user may no longer see the source. */
  readable: boolean
}

export type MessageStatus = 'done' | 'error' | 'stopped'

export interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  steps: ChatStep[]
  citations: Citation[]
  status: MessageStatus
  attachment_ids: number[]
  created_at: string
}

export type AttachmentState = 'queued' | 'processing' | 'ready' | 'failed'

export interface ChatAttachment {
  id: number
  name: string
  size: number
  state: AttachmentState
  detail: string
  title: string
  document_type: string
  chunk_count: number
}

export type FieldOwner = 'system' | 'assistant' | 'user'

export interface DraftField {
  label: string
  text: string
  owner: FieldOwner
  needs_input: boolean
  multiline: boolean
}

export type TableRowType = 'row' | 'group' | 'section' | 'total'
export type CellAlign = 'left' | 'center' | 'right'

/** A column of a table; a column with `children` is a group heading over them (two heading levels at most). */
export interface TableColumn {
  /** Stable id ("c3"); a column the canvas adds gets one from the server. */
  id?: string
  label: string
  align?: CellAlign
  /** Worked out by the server on every ordinary row ("c4 * c5"); such cells cannot be typed. */
  formula?: string
  children?: TableColumn[]
}

export interface TableRow {
  /** Stable id ("r12"); a row the canvas adds gets one from the server. */
  id?: string
  type: TableRowType
  /** One per leaf column; a `section` row has a single cell spanning the table. */
  cells: string[]
  /** Columns a `total` or `group` row adds up (computed by the server). */
  sum?: string[]
  scope?: 'all' | 'group'
}

/** A table block's spec (backend `app.drafting.tables`). Missing figures are "…". */
export interface TableSpec {
  columns: TableColumn[]
  rows: TableRow[]
  seq?: { c: number; r: number }
  landscape?: boolean
}

export type DraftBlockKind = 'heading' | 'para' | 'item' | 'table' | 'appendix'

export interface DraftBlock {
  id: string
  kind: DraftBlockKind
  /** For a table, a one-line summary; for an appendix, its title. */
  text: string
  owner: 'assistant' | 'user'
  proposal: DraftProposal | null
  /** Goes up each time the block's content changes. */
  version?: number
  table?: TableSpec
  /** Appendix: "Phụ lục" or "Phụ lục II". */
  label?: string
  /** Table or appendix: printed on a landscape page (only an appendix turns). */
  landscape?: boolean
  /** Table: its columns cannot show their longest word on its page. */
  too_wide?: boolean
  /** Table: cells still holding "…". */
  blanks?: number
  /** Table: what its formulas and sums could not work out. */
  problems?: string[]
  /** A passage quoting figures a table no longer holds. */
  stale?: { tables: string[]; figures: string[] }
}

/** The assistant's suggested change to a block: `replace` shows a diff, `delete` strikes the block, `insert` is a new block (the block's own text is empty). */
export interface DraftProposal {
  action: 'replace' | 'delete' | 'insert'
  text: string
  note: string
  /** Deterministic style warnings on a replacement (new facts, avoided wording), or what a proposed table lacks. */
  checks?: StyleFinding[]
  /** The proposed table, for a table block. */
  table?: TableSpec
  kind?: DraftBlockKind
}

/** One point from the style check: a warning the person should see before accepting. */
export interface StyleFinding {
  severity: 'warning' | 'info' | string
  message: string
  where?: string
}

/** Preset and detail level stored on the draft. */
export interface DraftStyle {
  preset: string
  detail: string
}

export interface StyleOption {
  id: string
  name: string
}

export interface StyleOptions {
  presets: StyleOption[]
  detail: StyleOption[]
}

export interface DraftHistoryEntry {
  version: number
  at: string
  by: 'assistant' | 'user'
  summary: string
}

export interface ChatDraft {
  id: number | string
  title: string
  version: number
  updated_at: string
  template: { code: string; kind: string; name: string; doc_type: string; authority: string }
  fields: Record<string, DraftField>
  blocks: DraftBlock[]
  missing: string[]
  /** The preset and detail level in force; absent on a draft saved before this existed. */
  style?: DraftStyle
  style_options?: StyleOptions
  history: DraftHistoryEntry[]
  /** The unit the draft is written for ("" = the author's own). */
  unit_id?: string
  unit_name?: string
}

export interface DraftFinding {
  severity: 'error' | 'warning' | 'info' | string
  message: string
  where: string
  /** The rule of Thông tư 68 the finding refers to (may be empty). */
  ref: string
}

export interface DraftStyleReport {
  wording: StyleFinding[]
  sections: StyleFinding[]
  /** Places still marked '…' for a person to fill in. */
  blanks: number
}

export interface DraftCheck {
  counts: { error: number; warning: number; manual: number }
  findings: DraftFinding[]
  checked_at: string
  style?: DraftStyleReport
}

export interface SessionDetail {
  session: ChatSession
  messages: ChatMessage[]
  attachments: ChatAttachment[]
  draft: ChatDraft | null
}

export interface SendBody {
  text: string
  attachment_ids?: number[]
  canvas?: boolean
  /** Set when the user selected text in the canvas and asked for a change. */
  context?: SelectionContext
}

/** A selected passage of the draft; `action` names the toolbar button used ("military" makes the server add the unit's style). */
export interface SelectionContext {
  block_id: string
  selection: string
  action?: string
}

export interface DraftPatch {
  fields?: Record<string, string>
  /** New text of a block, or the whole edited spec of a table block. */
  blocks?: { id: string; text?: string; table?: TableSpec }[]
  insert?: { after: string | null; kind: DraftBlockKind; text: string; table?: TableSpec }
  delete?: string[]
  style?: DraftStyle
  unit_id?: string
  /** Passages whose "figures changed" mark the user dismisses. */
  reviewed?: string[]
}

export interface StreamHandlers {
  onSession?: (event: { session_id: string; user_message_id: number; title: string }) => void
  /** The question was let through but the input screening objects to it: the text to show the person (the attempt is in the audit trail). */
  onModeration?: (event: { message: string; level: string; count: number }) => void
  onStep?: (step: ChatStep) => void
  onCanvas?: (draft: ChatDraft) => void
  onAnswer?: (event: { text: string; citations: Citation[] }) => void
  onError?: (message: string) => void
  onDone?: (event: { message_id: number; title: string; status: MessageStatus }) => void
}

/* ---------- plumbing ---------- */

/** Replaced by a constant at build time, so without the variable the mock (and its chunk) is dropped from the bundle. */
const MOCK = import.meta.env.VITE_MOCK_CHAT === '1'

async function call<T>(path: string, options?: RequestOptions): Promise<T> {
  if (MOCK) return (await import('../dev/mockChat')).mockRequest<T>(path, options)
  return request<T>(path, options)
}

const base = (sessionId: string) => `/api/chat/sessions/${sessionId}`

/** "att7" -> 7; a plain number or numeric text stays as it is; anything else gives null. */
export function attachmentIdOf(docId: number | string): number | null {
  const match = /^(?:att)?(\d+)$/.exec(String(docId))
  return match ? Number(match[1]) : null
}

/* ---------- sessions ---------- */

/** GET /api/chat/sessions (most recently updated first) */
export function listSessions(signal?: AbortSignal): Promise<ChatSession[]> {
  return call<ChatSession[]>('/api/chat/sessions', { signal })
}

/** POST /api/chat/sessions */
export function createSession(title?: string): Promise<ChatSession> {
  return call<ChatSession>('/api/chat/sessions', { method: 'POST', body: title ? { title } : {} })
}

/** GET /api/chat/sessions/{id} */
export function getSession(id: string, signal?: AbortSignal): Promise<SessionDetail> {
  return call<SessionDetail>(base(id), { signal })
}

/** PATCH /api/chat/sessions/{id} */
export function renameSession(id: string, title: string): Promise<ChatSession> {
  return call<ChatSession>(base(id), { method: 'PATCH', body: { title } })
}

/** DELETE /api/chat/sessions/{id} */
export function deleteSession(id: string): Promise<void> {
  return call<void>(base(id), { method: 'DELETE' })
}

/** DELETE that survives the page being closed (used to drop an empty conversation created by the focus warm-up). */
export function deleteSessionOnExit(id: string): void {
  const token = getToken()
  try {
    void fetch(base(id), { method: 'DELETE', keepalive: true, headers: token ? { Authorization: `Bearer ${token}` } : {} }).catch(() => undefined)
  } catch {
    // Best effort only.
  }
}

/** POST /api/chat/sessions/{id}/stop */
export function stopSession(id: string): Promise<void> {
  return call<void>(`${base(id)}/stop`, { method: 'POST' })
}

/**
 * POST /api/chat/sessions/{id}/warm: starts the assistant in the background so the first answer does not wait for
 * its ~10 s start-up. Fire and forget: failures are ignored.
 */
export function warmSession(id: string): void {
  if (MOCK) return
  void request<void>(`${base(id)}/warm`, { method: 'POST' }).catch(() => undefined)
}

/* ---------- streaming ---------- */

/** Delivers one server-sent event (`event:` name plus JSON `data:`) to the matching handler. */
function dispatch(block: string, handlers: StreamHandlers): void {
  let event = 'message'
  const data: string[] = []
  for (const line of block.split('\n')) {
    if (line.startsWith(':')) continue
    const colon = line.indexOf(':')
    const field = colon < 0 ? line : line.slice(0, colon)
    const value = colon < 0 ? '' : line.slice(colon + 1).replace(/^ /, '')
    if (field === 'event') event = value
    else if (field === 'data') data.push(value)
  }
  if (data.length === 0) return
  let payload: Record<string, unknown>
  try {
    payload = JSON.parse(data.join('\n')) as Record<string, unknown>
  } catch {
    return // a malformed event must not break the rest of the stream
  }
  switch (event) {
    case 'session':
      handlers.onSession?.(payload as unknown as Parameters<NonNullable<StreamHandlers['onSession']>>[0])
      break
    case 'moderation':
      handlers.onModeration?.(payload as unknown as Parameters<NonNullable<StreamHandlers['onModeration']>>[0])
      break
    case 'step':
      if (payload.step) handlers.onStep?.(payload.step as ChatStep)
      break
    case 'canvas':
      if (payload.draft) handlers.onCanvas?.(payload.draft as ChatDraft)
      break
    case 'answer':
      handlers.onAnswer?.({ text: String(payload.text ?? ''), citations: (payload.citations as Citation[] | undefined) ?? [] })
      break
    case 'error':
      handlers.onError?.(String(payload.message ?? 'Có lỗi xảy ra.'))
      break
    case 'done':
      handlers.onDone?.(payload as unknown as Parameters<NonNullable<StreamHandlers['onDone']>>[0])
      break
  }
}

/** Reads a `text/event-stream` body to its end and calls the handlers as events complete (blank-line separated). */
export async function readEventStream(stream: ReadableStream<Uint8Array>, handlers: StreamHandlers): Promise<void> {
  const reader = stream.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  const drain = (final: boolean) => {
    buffer = buffer.replace(/\r\n/g, '\n')
    let end = buffer.indexOf('\n\n')
    while (end >= 0) {
      dispatch(buffer.slice(0, end), handlers)
      buffer = buffer.slice(end + 2)
      end = buffer.indexOf('\n\n')
    }
    if (final && buffer.trim()) dispatch(buffer, handlers)
  }
  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      drain(false)
    }
    buffer += decoder.decode()
    drain(true)
  } finally {
    reader.releaseLock()
  }
}

async function failureOf(response: Response): Promise<ApiError> {
  let data: Record<string, unknown> = {}
  try {
    const parsed: unknown = await response.json()
    if (parsed && typeof parsed === 'object') data = parsed as Record<string, unknown>
  } catch {
    // Non-JSON error body.
  }
  if (response.status === 401) {
    clearToken()
    // The shared client owns the "session ended" handler; one authenticated call makes it run.
    void fetchCurrentUser().catch(() => undefined)
  }
  const detail = typeof data.detail === 'string' && data.detail ? data.detail : `Yêu cầu thất bại (mã ${response.status}).`
  return new ApiError(detail, response.status, data)
}

/**
 * POST /api/chat/sessions/{id}/messages and consume the event stream. Resolves when the stream closes; aborting
 * `signal` rejects with an AbortError. fetch is used instead of EventSource because the request needs a body and
 * the Authorization header.
 */
export async function streamMessage(sessionId: string, body: SendBody, handlers: StreamHandlers, signal: AbortSignal): Promise<void> {
  if (MOCK) {
    const { mockEventStream } = await import('../dev/mockChat')
    await readEventStream(mockEventStream(sessionId, body, signal), handlers)
    return
  }
  const token = getToken()
  let response: Response
  try {
    response = await fetch(`${base(sessionId)}/messages`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
      signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError('Không kết nối được máy chủ. Kiểm tra mạng nội bộ rồi thử lại.', 0)
  }
  if (!response.ok) throw await failureOf(response)
  if (!response.body) throw new ApiError('Máy chủ không trả về luồng dữ liệu.', 0)
  await readEventStream(response.body, handlers)
}

/* ---------- attachments ---------- */

/** POST /api/chat/sessions/{id}/attachments (multipart `file`) */
export function uploadAttachment(sessionId: string, file: File, onProgress: (fraction: number) => void): Promise<ChatAttachment> {
  if (MOCK) return import('../dev/mockChat').then((mock) => mock.mockUpload(sessionId, file, onProgress))
  const form = new FormData()
  form.append('file', file, file.name)
  return uploadForm<ChatAttachment>(`${base(sessionId)}/attachments`, form, onProgress)
}

/** GET /api/chat/sessions/{id}/attachments/{aid} */
export function getAttachment(sessionId: string, attachmentId: number, signal?: AbortSignal): Promise<ChatAttachment> {
  return call<ChatAttachment>(`${base(sessionId)}/attachments/${attachmentId}`, { signal })
}

/** DELETE /api/chat/sessions/{id}/attachments/{aid} */
export function deleteAttachment(sessionId: string, attachmentId: number): Promise<void> {
  return call<void>(`${base(sessionId)}/attachments/${attachmentId}`, { method: 'DELETE' })
}

/** GET .../attachments/{aid}/content */
export function getAttachmentContent(sessionId: string, attachmentId: number, signal?: AbortSignal): Promise<Paragraph[]> {
  return call<Paragraph[]>(`${base(sessionId)}/attachments/${attachmentId}/content`, { signal })
}

/** The text of a cited source: a store document or a chat attachment. */
export function getSourceContent(
  source: { kind: 'store' | 'attachment'; docId: number | string },
  sessionId: string,
  signal?: AbortSignal,
): Promise<Paragraph[]> {
  const id = attachmentIdOf(source.docId)
  if (id === null) return Promise.reject(new ApiError('Không xác định được văn bản nguồn.', 0))
  if (source.kind === 'attachment') return getAttachmentContent(sessionId, id, signal)
  return call<Paragraph[]>(`/api/documents/${id}/content`, { signal })
}

/* ---------- draft (Canvas) ---------- */

/** GET /api/chat/sessions/{id}/draft */
export function getDraft(sessionId: string, signal?: AbortSignal): Promise<ChatDraft | null> {
  return call<ChatDraft | null>(`${base(sessionId)}/draft`, { signal })
}

/** PATCH /api/chat/sessions/{id}/draft: the user's own edits. */
export function patchDraft(sessionId: string, patch: DraftPatch): Promise<ChatDraft> {
  return call<ChatDraft>(`${base(sessionId)}/draft`, { method: 'PATCH', body: patch })
}

/** POST .../draft/blocks/{block}/accept */
export function acceptProposal(sessionId: string, blockId: string): Promise<ChatDraft> {
  return call<ChatDraft>(`${base(sessionId)}/draft/blocks/${encodeURIComponent(blockId)}/accept`, { method: 'POST' })
}

/** POST .../draft/blocks/{block}/reject */
export function rejectProposal(sessionId: string, blockId: string): Promise<ChatDraft> {
  return call<ChatDraft>(`${base(sessionId)}/draft/blocks/${encodeURIComponent(blockId)}/reject`, { method: 'POST' })
}

/** POST .../draft/check: format check of the DOCX built from the draft. */
export function checkDraft(sessionId: string): Promise<DraftCheck> {
  return call<DraftCheck>(`${base(sessionId)}/draft/check`, { method: 'POST' })
}

/** GET .../draft/export as a .docx blob. */
export async function exportDraft(sessionId: string): Promise<Blob> {
  if (MOCK) return (await import('../dev/mockChat')).mockExport()
  return requestBlob(`${base(sessionId)}/draft/export`)
}

/** POST .../draft/save: stores the draft in the document store ({document} on the wire). */
export async function saveDraft(sessionId: string, declaredSecret: boolean): Promise<DocumentSummary> {
  const saved = await call<{ document: DocumentSummary }>(`${base(sessionId)}/draft/save`, { method: 'POST', body: { declared_secret: declaredSecret } })
  return saved.document
}

/** POST .../draft: opens an empty draft of a template kind ("CV", "KH"...); 409 when one exists and `replace` is false. */
export function createDraft(sessionId: string, kind: string, replace = false): Promise<ChatDraft> {
  return call<ChatDraft>(`${base(sessionId)}/draft`, { method: 'POST', body: { kind, replace } })
}

/** DELETE .../draft */
export function deleteDraft(sessionId: string): Promise<void> {
  return call<void>(`${base(sessionId)}/draft`, { method: 'DELETE' })
}
