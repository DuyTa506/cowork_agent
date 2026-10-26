import { documentsApi, type DocumentDetail, type DocumentState, type DocumentSummary, type ProcessingStep, type User } from '../api'
import type { IconName } from '../components/Icon'
import { formatNumber } from './format'

export type StateTabKey = 'all' | 'ready' | 'processing' | 'review' | 'attention'

export interface StateTab {
  key: StateTabKey
  label: string
  /** States the group covers; empty means every state. */
  states: DocumentState[]
  /** Colour of the bar on the stat card. */
  tone: 'ink' | 'green' | 'blue' | 'amber'
  icon: IconName
}

/** The grouping of the state filter on the document list (the four stat cards). */
export const STATE_TABS: StateTab[] = [
  { key: 'all', label: 'Tất cả', states: [], tone: 'ink', icon: 'folder' },
  { key: 'ready', label: 'Sẵn sàng', states: ['ready'], tone: 'green', icon: 'checkCircle' },
  { key: 'processing', label: 'Đang xử lý', states: ['uploaded', 'processing'], tone: 'blue', icon: 'spinner' },
  { key: 'attention', label: 'Cần xử lý', states: ['needs_review', 'needs_ocr', 'failed'], tone: 'amber', icon: 'alert' },
]

const BREAKDOWN_LABELS: Record<DocumentState, string> = {
  uploaded: 'chờ',
  processing: 'đang chạy',
  ready: 'sẵn sàng',
  needs_review: 'cần rà soát',
  needs_ocr: 'cần OCR',
  failed: 'lỗi',
}

/** "1 cần rà soát · 2 lỗi": the non-empty states behind a group count (empty when the group is a single state). */
export function tabBreakdown(tab: StateTab, counts: Partial<Record<DocumentState, number>>): string {
  if (tab.states.length < 2) return ''
  return tab.states
    .filter((state) => (counts[state] ?? 0) > 0)
    .map((state) => `${formatNumber(counts[state] ?? 0)} ${BREAKDOWN_LABELS[state]}`)
    .join(' · ')
}

/** Number of documents in a tab given the per-state counts from the API. */
export function tabCount(tab: StateTab, counts: Partial<Record<DocumentState, number>>): number {
  const values = tab.states.length > 0 ? tab.states.map((state) => counts[state] ?? 0) : Object.values(counts)
  return values.reduce((sum, value) => sum + value, 0)
}

/** True while the worker still has to handle the document (the list should keep refreshing). */
export function isInProgress(document: Pick<DocumentSummary, 'state'>): boolean {
  return document.state === 'uploaded' || document.state === 'processing'
}

/** "24/KH-PTM"; "…/CV-PCT" when the number is missing; the file name when nothing was recognised. */
export function documentSymbol(document: DocumentSummary): string {
  const { document_number: number, symbol } = document
  if (number && symbol) return number.includes('/') ? number : `${number}/${symbol}`
  if (symbol) return `…/${symbol}`
  return number || document.original_name
}

/** Title for display; the file name stands in until the parser has found one. */
export function documentTitle(document: Pick<DocumentSummary, 'title' | 'original_name'>): string {
  return document.title.trim() || document.original_name
}

/** The small grey line under the title in the list. */
export function documentNote(document: DocumentSummary): string {
  if (document.state === 'ready' || document.state === 'needs_review') {
    if (document.state === 'needs_review' && document.state_detail) return document.state_detail
    if (document.level === 'mat') return 'Chỉ chỉ huy được xem'
    return document.chunk_count > 0 ? `${formatNumber(document.chunk_count)} đoạn · đã lập chỉ mục` : 'Chưa có đoạn nào'
  }
  if (document.state === 'uploaded') return 'Đang chờ xử lý'
  if (document.state === 'processing') return document.state_detail || 'Đang xử lý'
  return document.state_detail || (document.state === 'needs_ocr' ? 'Chờ OCR' : 'Không xử lý được')
}

/** Required fields that are still empty on a document (highlighted for manual completion). */
export function missingFields(document: Pick<DocumentDetail, 'subject' | 'document_type' | 'issued_date'>): string[] {
  const missing: string[] = []
  if (!document.subject.trim()) missing.push('subject')
  if (!document.document_type.trim()) missing.push('document_type')
  if (!document.issued_date) missing.push('issued_date')
  return missing
}

/** True when the user may edit, reprocess or delete the document (its uploader or an administrator); the server enforces it too. */
export function canManage(document: Pick<DocumentSummary, 'uploaded_by_id'>, user: Pick<User, 'id' | 'role'> | null): boolean {
  return user !== null && (user.role === 'admin' || user.id === document.uploaded_by_id)
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

/** Downloads the original file of a document. */
export async function downloadOriginal(document: Pick<DocumentSummary, 'id' | 'original_name'>): Promise<void> {
  saveBlob(await documentsApi.fetchOriginalFile(document.id), document.original_name)
}

/** Seconds as "0,8 giây", "12 giây" or "1 phút 5 giây". */
export function formatDuration(milliseconds: number): string {
  const seconds = Math.max(0, milliseconds) / 1000
  if (seconds < 0.1) return '< 0,1 giây'
  if (seconds < 10) return `${new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 1, minimumFractionDigits: seconds < 1 ? 1 : 0 }).format(seconds)} giây`
  if (seconds < 60) return `${Math.round(seconds)} giây`
  const minutes = Math.floor(seconds / 60)
  const rest = Math.round(seconds % 60)
  return rest === 0 ? `${minutes} phút` : `${minutes} phút ${rest} giây`
}

function timestampMs(value: string | null): number | null {
  if (!value) return null
  const time = new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(value) ? value : `${value}Z`).getTime()
  return Number.isNaN(time) ? null : time
}

/**
 * How long each finished step took: the time since the previous step finished. The first step has no known start (the file may
 * have waited in the queue, or been reprocessed long after the upload), so its duration is null.
 */
export function stepDurations(steps: ProcessingStep[]): (number | null)[] {
  let previous: number | null = null
  return steps.map((step) => {
    const end = step.state === 'done' || step.state === 'failed' ? timestampMs(step.at) : null
    if (end === null) return null
    const duration = previous === null ? null : end - previous
    previous = end
    return duration
  })
}
