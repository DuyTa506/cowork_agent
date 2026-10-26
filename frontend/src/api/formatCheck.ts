import { getToken } from '../auth/tokenStorage'
import { request, requestBlob, uploadForm } from './client'
import type { DocumentSummary } from './types'

/** Types mirror docs/FORMAT_CHECK_API.md (the `result` payload is doccheck's display data, all text already Vietnamese). */

/** Confidence of an automatic fix: `cao` and `trungbinh` are ticked by default, `thap` is not. */
export type Tier = 'cao' | 'trungbinh' | 'thap'
export type Severity = 'error' | 'warning' | 'info'
export type CheckKind = 'word' | 'pdf'
/** `track` leaves Word tracked changes, `apply` writes the new format directly. */
export type FixMode = 'track' | 'apply'
export type SaveWhich = 'fixed' | 'original'
export type CheckFile = 'file' | 'fixed' | 'report' | 'annotated'

export interface CheckProfile {
  id: string
  label: string
  experimental: boolean
}

/** GET /options: what the screen offers before a file is chosen. */
export interface CheckOptions {
  profiles: CheckProfile[]
  default_profile: string
  default_spell: boolean
  /** Accepted extensions, for example `.docx`. */
  accept: string[]
  max_mb: number
  retention_hours: number
}

/** A format finding that belongs to no paragraph (for example a missing element). */
export interface CheckBanner {
  severity: Severity
  rule: string
  message: string
  actual: string
}

/** Spelling error position in `text` (UTF-16 index, so usable with `String.slice`): `[start, end, itemId | null, tier | null]`. */
export type CheckMark = [number, number, string | null, Tier | null]

/** One paragraph of the preview. */
export interface CheckPara {
  pi: number
  where: 'body' | 'cell' | 'textbox' | string
  table: number | null
  row: number | null
  col: number | null
  text: string
  label: string
  blank: boolean
  bold: boolean
  align: string
  /** Real page of a PDF (1-based), null for Word. */
  page: number | null
  /** Page estimated from font metrics (Word only; Word's own breaks may differ). */
  pg: number | null
  pbb?: boolean
  /** Format messages of this paragraph. */
  msgs: string[]
  marks: CheckMark[]
}

/** A fix the user can tick; its `id` goes to /fix. Spelling items add `found`, `raw_after`, `ctx`, `start`, `end`. */
export interface CheckItem {
  id: string
  kind: 'format' | 'layout' | 'pagenum' | 'spelling' | string
  prop: string
  label: string
  before: string
  after: string
  explain: string
  /** Legal basis, for example "Phụ lục I, tr.12". */
  basis: string
  tier: Tier
  group: string
  pi: number | null
  /** Id of the item that must be selected together with this one. */
  requires: string | null
  /** Always applied, cannot be told apart from the rest. */
  locked: boolean
  legacy?: boolean
  rules: string[]
  section?: number | null
  details?: string[]
  found?: string
  raw_after?: string
  ctx?: [string, string]
  start?: number
  end?: number
  layer?: string
  score?: number | null
}

/** A finding that has to be fixed by hand. */
export interface CheckManual {
  id: string
  rule: string
  pis: number[]
  severity: Severity
  message: string
  reason: string
  found: string
  suggestion: string
  label?: string
  ctx?: [string, string]
}

export interface CheckResult {
  sid?: string
  name?: string
  facts: { doc_type: string | null; origin: string | null }
  counts: { format: number; spelling: number; items: number; manual: number }
  banner: CheckBanner[]
  paras: CheckPara[]
  est_pages?: boolean
  items: CheckItem[]
  manual: CheckManual[]
  tiers: Record<Tier, string>
  kind: CheckKind
  kind_label: string
  can_fix: boolean
  /** PDF: "không sửa trực tiếp được". */
  note: string
  profile: CheckProfile
}

/** A checked file (POST /, GET /{id}, POST /{id}/recheck). */
export interface CheckSession {
  id: string
  name: string
  size: number
  kind: CheckKind
  can_fix: boolean
  profile: string
  spell: boolean
  /** A corrected copy exists. */
  fixed: boolean
  counts: { format: number; spelling: number }
  created_at: string
  /** ISO UTC with zone. */
  expires_at: string
  result: CheckResult
}

export interface FixFailure {
  id: string
  reason: string
}

/** POST /{id}/fix: `after` is a fresh check of the corrected copy. */
export interface FixResult {
  applied: string[]
  failed: FixFailure[]
  after: { format: number; spelling: number }
}

export interface RecheckOptions {
  profile?: string
  spell?: boolean
}

const BASE = '/api/format-check'

/** GET /options */
export function getOptions(signal?: AbortSignal): Promise<CheckOptions> {
  return request<CheckOptions>(`${BASE}/options`, { signal })
}

/** POST / (multipart) with upload progress; the server checks the file before it answers, so the promise settles after both. */
export function uploadFile(file: File, options: RecheckOptions, onProgress: (fraction: number) => void): Promise<CheckSession> {
  const form = new FormData()
  form.append('file', file, file.name)
  if (options.profile) form.append('profile', options.profile)
  if (options.spell !== undefined) form.append('spell', String(options.spell))
  return uploadForm<CheckSession>(BASE, form, onProgress)
}

/** GET /{id} */
export function getCheck(id: string, signal?: AbortSignal): Promise<CheckSession> {
  return request<CheckSession>(`${BASE}/${id}`, { signal })
}

/** POST /{id}/recheck: checks the original again (any corrected copy is dropped). */
export function recheck(id: string, options: RecheckOptions): Promise<CheckSession> {
  return request<CheckSession>(`${BASE}/${id}/recheck`, { method: 'POST', body: options })
}

/**
 * POST /{id}/fix. The corrected copy is rebuilt from the original each time, so `ids` must hold every edit wanted in it,
 * including the ones applied earlier.
 */
export function fix(id: string, ids: string[], mode: FixMode): Promise<FixResult> {
  return request<FixResult>(`${BASE}/${id}/fix`, { method: 'POST', body: { ids, mode } })
}

/** POST /{id}/save: puts the original or corrected file into the document store. */
export function saveToStore(id: string, which: SaveWhich, declaredSecret: boolean): Promise<DocumentSummary> {
  return request<DocumentSummary>(`${BASE}/${id}/save`, { method: 'POST', body: { which, declared_secret: declaredSecret } })
}

/** DELETE /{id} */
export function deleteCheck(id: string): Promise<void> {
  return request<void>(`${BASE}/${id}`, { method: 'DELETE' })
}

/**
 * Deletes a session when the user leaves: the request survives the page being closed (`keepalive`) and failures are
 * ignored, because the server removes expired sessions anyway.
 */
export function discardCheck(id: string): void {
  const token = getToken()
  try {
    void fetch(`${BASE}/${id}`, { method: 'DELETE', keepalive: true, headers: token ? { Authorization: `Bearer ${token}` } : {} }).catch(() => undefined)
  } catch {
    // Nothing more can be done while leaving.
  }
}

/** GET /{id}/file | fixed | report | annotated as a blob (these endpoints need the Authorization header). */
export function fetchFile(id: string, file: CheckFile): Promise<Blob> {
  return requestBlob(`${BASE}/${id}/${file}`)
}

/** The file name the server gives each download, rebuilt here because `requestBlob` does not expose headers. */
export function downloadName(session: Pick<CheckSession, 'name'>, file: CheckFile): string {
  const dot = session.name.lastIndexOf('.')
  const stem = dot > 0 ? session.name.slice(0, dot) : session.name
  if (file === 'fixed') return `${stem}_da_sua.docx`
  if (file === 'annotated') return `${stem}_ghi_chu.docx`
  if (file === 'report') return `${stem}_bao_cao.txt`
  return session.name
}

/** Saves a blob under a file name through a temporary link. */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = window.document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
