/**
 * Types mirroring the backend's OpenAPI schemas (docs/openapi.json).
 * Endpoints documented as free-form objects (settings, units) are typed from the backend source.
 */

export type Role = 'admin' | 'commander' | 'reviewer' | 'staff'

export interface User {
  id: number
  username: string
  full_name: string
  unit_id: string
  unit_name: string
  role: Role
  is_active: boolean
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user: User
}

export interface Unit {
  id: string
  name: string
  type: string
  parent: string
  depth: number
  provisional: boolean
}

export type DocumentState = 'uploaded' | 'processing' | 'ready' | 'needs_review' | 'needs_ocr' | 'failed'
/** `thuong` = ordinary, `mat` = secret (visible to commanders only). */
export type DocumentLevel = 'thuong' | 'mat'

export interface DocumentSummary {
  id: number
  original_name: string
  title: string
  /** Trích yếu as printed ("V/v ..."). */
  subject: string
  document_type: string
  document_number: string
  symbol: string
  issuer: string
  /** ISO `yyyy-mm-dd`, empty when unknown. */
  issued_date: string
  signer: string
  unit_id: string
  unit_name: string
  level: DocumentLevel
  state: DocumentState
  state_detail: string
  file_size: number
  chunk_count: number
  uploaded_by_id: number
  uploaded_by_name: string
  uploaded_at: string
  updated_at: string
  /** Computed tags first (year, topic, scan), then hand-made ones. */
  tags: string[]
}

export type StepState = 'pending' | 'running' | 'done' | 'failed'

export interface ProcessingStep {
  key: string
  label: string
  state: StepState
  detail: string
  at: string | null
}

export interface DocumentDetail extends DocumentSummary {
  steps: ProcessingStep[]
  warnings: string[]
  secret_reasons: string[]
  can_manage: boolean
  /** The part of `tags` a person set; only these can be edited. */
  manual_tags: string[]
}

export interface FacetValue {
  value: string
  count: number
}

/** GET /api/documents/facets: what the browse panel can filter by, with counts of readable documents. */
export interface Facets {
  /** value = unit id; documents directly in that unit (the panel adds up the subtree). */
  units: FacetValue[]
  types: FacetValue[]
  years: FacetValue[]
  tags: FacetValue[]
}

export interface DocumentPage {
  items: DocumentSummary[]
  total: number
  /** Count of readable documents per state. */
  states: Partial<Record<DocumentState, number>>
}

/** Fields a user may correct by hand (PATCH body). */
export interface MetadataUpdate {
  title?: string
  subject?: string
  document_type?: string
  document_number?: string
  symbol?: string
  issuer?: string
  issued_date?: string
  signer?: string
}

/** One paragraph of the document viewer; `pi` is the source index that citations refer to. */
export interface Paragraph {
  pi: number
  text: string
  align: 'left' | 'center' | 'right' | 'justify' | string
  bold: boolean
  italic: boolean
  table: number | null
  row: number | null
  col: number | null
}

/** A block of a scanned page found by OCR: kind, position (x0, y0, x1, y1 on a 0-1000 scale of the page), text and the viewer paragraphs written from it. */
export interface ScanBlock {
  page: number
  label: string
  box: [number, number, number, number]
  text: string
  pi: [number, number] | null
}

/** GET /api/documents/{id}/scan */
export interface Scan {
  pages: number
  blocks: ScanBlock[]
}

export interface UploadItem {
  name: string
  document: DocumentSummary | null
  error: string
  /** `duplicate`, `error` or empty on success. */
  code: string
  existing_id: number | null
}

export interface UploadResult {
  items: UploadItem[]
}

export interface UserCreate {
  username: string
  password: string
  full_name: string
  unit_id: string
  role: Role
}

export interface UserUpdate {
  full_name?: string
  unit_id?: string
  role?: Role
  is_active?: boolean
  password?: string
}

export interface AuditEntry {
  id: number
  username: string
  action: string
  entity_type: string
  entity_id: string
  detail: string
  ip_address: string
  created_at: string
}

export type SettingKind = 'str' | 'int' | 'float' | 'bool' | 'choice' | 'url'

/** A secret field never carries its value, only whether one is stored. */
export interface SecretState {
  set: boolean
}

export type SettingValue = string | number | boolean | SecretState

export interface SettingField {
  name: string
  label: string
  kind: SettingKind
  help: string
  secret: boolean
  choices: string[]
  minimum: number | null
  maximum: number | null
  value: SettingValue
}

export interface SettingsSection {
  key: string
  label: string
  description: string
  used_by: string
  sends_document_text: boolean
  fields: SettingField[]
}

export interface PublicSettings {
  sections: SettingsSection[]
  confirmed_hosts: string[]
  embedding: { fingerprint: string; collection: string }
}

/** GET /api/admin/settings */
export interface SettingsOverview extends PublicSettings {
  pending_jobs: number
}

/** Values sent to the backend: a secret is `null` (keep), `""` (clear) or the new string. */
export type SettingsPayload = Record<string, string | number | boolean | null>

export interface SaveSettingsResult {
  changed: string[]
  reindex_required: boolean
  settings: PublicSettings
}

export interface TestConnectionResult {
  ok: boolean
  message: string
  latency_ms: number
  detail: Record<string, unknown>
}

export interface ReindexResult {
  queued: number
}
