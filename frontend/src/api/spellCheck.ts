import { getToken } from '../auth/tokenStorage'
import { request, requestBlob, uploadForm } from './client'
import type { CheckBanner, CheckItem, CheckManual, CheckPara, Tier } from './formatCheck'

/** Types mirror docs/SPELLCHECK_API.md (the `result` payload is doccheck's display data reduced to spelling, all text Vietnamese). */

/** A Word file, a text-layer PDF, or text (pasted, .txt, .md). PDF cannot be corrected, only listed. */
export type SpellKind = 'word' | 'pdf' | 'text'
export type FixMode = 'track' | 'apply'
export type SpellFile = 'file' | 'fixed' | 'report'

export interface SpellOptions {
  /** Accepted extensions, for example `.docx`. */
  accept: string[]
  max_mb: number
  /** Longest text that is checked, in characters. */
  max_chars: number
  retention_hours: number
}

export interface SpellResult {
  paras: CheckPara[]
  items: CheckItem[]
  manual: CheckManual[]
  banner: CheckBanner[]
  tiers: Record<Tier, string>
  counts: { format: number; spelling: number; items: number; manual: number }
  kind: SpellKind
  kind_label: string
  can_fix: boolean
  /** PDF: why it cannot be corrected. */
  note: string
  chars: number
  est_pages?: boolean
  /** Findings hidden by the ignore list. */
  ignored: number
  markdown?: boolean
  /** Text: how to write the file back. */
  file?: { enc: string; eol: string }
}

/** A checked file or text (POST /, POST /text, GET /{id}, PUT /{id}/ignore). */
export interface SpellSession {
  id: string
  name: string
  size: number
  kind: SpellKind
  can_fix: boolean
  fixed: boolean
  counts: { spelling: number }
  /** Words skipped in this session. */
  ignore: string[]
  created_at: string
  /** ISO UTC with zone. */
  expires_at: string
  result: SpellResult
}

export interface FixFailure {
  id: string
  reason: string
}

/** POST /{id}/fix: `after.spelling` is what a new check of the corrected copy still finds; `text` is the corrected text (text sessions). */
export interface SpellFixResult {
  applied: string[]
  failed: FixFailure[]
  after: { spelling: number }
  text: string | null
}

const BASE = '/api/spellcheck'

/** GET /options */
export function getOptions(signal?: AbortSignal): Promise<SpellOptions> {
  return request<SpellOptions>(`${BASE}/options`, { signal })
}

/** POST / (multipart) with upload progress; the server checks the file before it answers. */
export function uploadFile(file: File, markdown: boolean | undefined, onProgress: (fraction: number) => void): Promise<SpellSession> {
  const form = new FormData()
  form.append('file', file, file.name)
  if (markdown !== undefined) form.append('markdown', String(markdown))
  return uploadForm<SpellSession>(BASE, form, onProgress)
}

/** POST /text */
export function checkText(text: string, markdown: boolean): Promise<SpellSession> {
  return request<SpellSession>(`${BASE}/text`, { method: 'POST', body: { text, markdown } })
}

/** GET /{id} */
export function getSession(id: string, signal?: AbortSignal): Promise<SpellSession> {
  return request<SpellSession>(`${BASE}/${id}`, { signal })
}

/** PUT /{id}/ignore: the complete list of words to skip (empty list clears it). */
export function setIgnored(id: string, words: string[]): Promise<SpellSession> {
  return request<SpellSession>(`${BASE}/${id}/ignore`, { method: 'PUT', body: { words } })
}

/** POST /{id}/fix. The corrected copy is rebuilt from the original each time, so `ids` must hold every edit wanted in it. */
export function fix(id: string, ids: string[], mode: FixMode): Promise<SpellFixResult> {
  return request<SpellFixResult>(`${BASE}/${id}/fix`, { method: 'POST', body: { ids, mode } })
}

/** DELETE /{id} */
export function deleteSession(id: string): Promise<void> {
  return request<void>(`${BASE}/${id}`, { method: 'DELETE' })
}

/** Deletes a session when the user leaves: survives the page being closed (`keepalive`); failures are ignored (the server expires it anyway). */
export function discardSession(id: string): void {
  const token = getToken()
  try {
    void fetch(`${BASE}/${id}`, { method: 'DELETE', keepalive: true, headers: token ? { Authorization: `Bearer ${token}` } : {} }).catch(() => undefined)
  } catch {
    // Nothing more can be done while leaving.
  }
}

/** GET /{id}/file | fixed | report as a blob (these endpoints need the Authorization header). */
export function fetchFile(id: string, file: SpellFile): Promise<Blob> {
  return requestBlob(`${BASE}/${id}/${file}`)
}

/** The file name the server gives each download, rebuilt here because `requestBlob` does not expose headers. */
export function downloadName(session: Pick<SpellSession, 'name' | 'kind'>, file: SpellFile): string {
  const dot = session.name.lastIndexOf('.')
  const stem = dot > 0 ? session.name.slice(0, dot) : session.name
  const ext = dot > 0 ? session.name.slice(dot) : '.txt'
  if (file === 'fixed') return session.kind === 'text' ? `${stem}_sua${ext}` : `${stem}_sua.docx`
  if (file === 'report') return `${stem}_chinh_ta.txt`
  return session.name
}

export { saveBlob } from './formatCheck'
