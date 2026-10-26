import { chatApi } from '../../api'
import type { ChatAttachment, ChatMessage, Citation, StepDocumentRef } from '../../api/chat'

/** A message as the screen keeps it: server messages plus the turn that is being streamed right now. */
export type UiMessage = Omit<ChatMessage, 'status'> & {
  /** Stable React key, so the live message does not remount when the server gives it its real id. */
  key: string
  status: ChatMessage['status'] | 'running'
  /** True for answers received in this visit: they are revealed with the typing effect. */
  fresh?: boolean
  /** Error text shown under the message. */
  error?: string
  /** Wall-clock start of a turn started in this visit (ms since epoch); drives the running timer. */
  startedAt?: number
  /** Total time of a turn that finished in this visit. */
  durationMs?: number
}

/** A document the side panel can show. */
export interface SourceRef {
  /** Identity of the source (kind + document), so opening it again reuses the tab. */
  key: string
  kind: 'store' | 'attachment'
  /** Store document id, or the attachment id. */
  id: number
  title: string
  ref: string
  section: string
  text: string
  /** Paragraph range to highlight, null when unknown. */
  pi: [number, number] | null
  n: number | null
  readable: boolean
}

/** A file in the composer: uploading, being indexed, ready or failed. */
export interface ComposerFile {
  key: string
  name: string
  size: number
  /** Upload progress, 0..1. */
  progress: number
  attachment: ChatAttachment | null
  /** Why the upload failed. */
  error: string | null
}

export function sourceFromCitation(citation: Citation): SourceRef | null {
  const id = chatApi.attachmentIdOf(citation.doc_id)
  if (id === null) return null
  const [from, to] = citation.pi
  return {
    key: `${citation.kind}:${id}`,
    kind: citation.kind,
    id,
    title: citation.title,
    ref: citation.ref,
    section: citation.section,
    text: citation.text,
    pi: from >= 0 && to >= from ? [from, to] : null,
    n: citation.n,
    readable: citation.readable,
  }
}

/** A document named by a tool step; chat attachments have ids such as "att3". */
export function sourceFromStepRef(reference: StepDocumentRef): SourceRef | null {
  const id = chatApi.attachmentIdOf(reference.doc_id)
  if (id === null) return null
  const kind = String(reference.doc_id).startsWith('att') ? 'attachment' : 'store'
  // The label reads "Quyết định 33/QĐ-QK3 (13/10/2026) - QUÂN KHU 3 - Về việc ..."; its first part is the short name.
  const short = reference.label.split(/\s+[(-]\s*/)[0] || reference.label
  return { key: `${kind}:${id}`, kind, id, title: reference.label, ref: short, section: reference.section, text: '', pi: null, n: null, readable: true }
}
