import { request, requestBlob, uploadForm } from './client'
import type {
  DocumentDetail,
  DocumentPage,
  DocumentState,
  DocumentSummary,
  Facets,
  MetadataUpdate,
  Paragraph,
  Scan,
  UploadResult,
} from './types'

export interface DocumentQuery {
  q?: string
  /** Several states are merged client-side because the API filters by one state only. */
  states?: DocumentState[]
  /** Comma-separated types: a document matches any of them. */
  documentType?: string
  unitId?: string
  level?: string
  /** A document must carry every one of these. */
  tags?: string[]
  /** ISO dates. */
  dateFrom?: string
  dateTo?: string
  limit: number
  offset: number
}

/** The API's maximum page size. */
const MAX_PAGE = 200

function listParams(query: DocumentQuery, limit: number, offset: number, state?: DocumentState) {
  return {
    q: query.q,
    state,
    document_type: query.documentType,
    unit_id: query.unitId,
    level: query.level,
    tag: query.tags,
    date_from: query.dateFrom,
    date_to: query.dateTo,
    limit,
    offset,
  }
}

/** Newest upload first, the order the API uses by default. */
function byNewest(a: DocumentSummary, b: DocumentSummary): number {
  return b.uploaded_at.localeCompare(a.uploaded_at) || b.id - a.id
}

/**
 * GET /api/documents. For a group of states (for example uploaded + processing) each state is fetched up to the end of the
 * requested page and the results are merged, which stays correct for the default ordering; groups are small in practice.
 */
export async function listDocuments(query: DocumentQuery, signal?: AbortSignal): Promise<DocumentPage> {
  const states = query.states ?? []
  if (states.length <= 1) {
    return request<DocumentPage>('/api/documents', { query: listParams(query, query.limit, query.offset, states[0]), signal })
  }
  const window = Math.min(query.offset + query.limit, MAX_PAGE)
  const pages = await Promise.all(
    states.map((state) => request<DocumentPage>('/api/documents', { query: listParams(query, window, 0, state), signal })),
  )
  const items = pages
    .flatMap((page) => page.items)
    .sort(byNewest)
    .slice(query.offset, query.offset + query.limit)
  return { items, total: pages.reduce((sum, page) => sum + page.total, 0), states: pages[0]?.states ?? {} }
}

/** GET /api/documents/{id} */
export function getDocument(id: number, signal?: AbortSignal): Promise<DocumentDetail> {
  return request<DocumentDetail>(`/api/documents/${id}`, { signal })
}

/** GET /api/documents/{id}/content */
export function getDocumentContent(id: number, signal?: AbortSignal): Promise<Paragraph[]> {
  return request<Paragraph[]>(`/api/documents/${id}/content`, { signal })
}

/** GET /api/documents/{id}/scan: the pages of a scanned document with the blocks OCR found on them (404 when it has none). */
export function getDocumentScan(id: number, signal?: AbortSignal): Promise<Scan> {
  return request<Scan>(`/api/documents/${id}/scan`, { signal })
}

/** PATCH /api/documents/{id} */
export function updateDocument(id: number, changes: MetadataUpdate): Promise<DocumentDetail> {
  return request<DocumentDetail>(`/api/documents/${id}`, { method: 'PATCH', body: changes })
}

/** POST /api/documents/{id}/reprocess */
export function reprocessDocument(id: number): Promise<DocumentDetail> {
  return request<DocumentDetail>(`/api/documents/${id}/reprocess`, { method: 'POST' })
}

/** DELETE /api/documents/{id} */
export function deleteDocument(id: number): Promise<void> {
  return request<void>(`/api/documents/${id}`, { method: 'DELETE' })
}

/** GET /api/documents/{id}/file as a blob (the endpoint needs the Authorization header, so a plain link cannot be used). */
export function fetchOriginalFile(id: number): Promise<Blob> {
  return requestBlob(`/api/documents/${id}/file`)
}

/** POST /api/documents (multipart). Each file succeeds or fails on its own; see `UploadResult.items`. */
export function uploadDocuments(
  files: File[],
  declaredSecret: boolean,
  onProgress: (fraction: number) => void,
): Promise<UploadResult> {
  const form = new FormData()
  form.append('declared_secret', String(declaredSecret))
  for (const file of files) form.append('files', file, file.name)
  return uploadForm<UploadResult>('/api/documents', form, onProgress)
}

/** GET /api/documents/facets */
export function getFacets(signal?: AbortSignal): Promise<Facets> {
  return request<Facets>('/api/documents/facets', { signal })
}

/** PUT /api/documents/{id}/tags: replaces the hand-made tags (computed ones stay). */
export function setTags(id: number, tags: string[]): Promise<DocumentDetail> {
  return request<DocumentDetail>(`/api/documents/${id}/tags`, { method: 'PUT', body: { tags } })
}
