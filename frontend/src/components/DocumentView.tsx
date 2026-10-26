import { lazy, Suspense, useState } from 'react'
import { ApiError, documentsApi, type Paragraph } from '../api'
import { useAsyncData } from '../hooks/useAsyncData'
import { DocumentViewer, type ViewerHighlight } from './DocumentViewer'
import { Spinner } from './Spinner'

// pdf.js is large: it is fetched when the first page view is opened, not with the app
const PdfViewer = lazy(() => import('./PdfViewer').then((module) => ({ default: module.PdfViewer })))

interface DocumentViewProps {
  documentId: number
  highlight?: ViewerHighlight
  /** The cited passage, to find it on the pages of a PDF (without it the paragraphs of `highlight` are used). */
  snippet?: string
  className?: string
  baseFontPx?: number
  /** Loads the paragraphs from somewhere other than the document store (a chat attachment). */
  loadContent?: (signal: AbortSignal) => Promise<Paragraph[]>
  /** Show the document's own pages (default: only for store documents, that is when `loadContent` is not given). */
  tryPages?: boolean
}

type Mode = 'page' | 'text'

/**
 * Shows a document the way it should be read: its own pages as the server's PDF drawn by pdf.js (the original, or the one made from a
 * Word file), with the OCR blocks over a scan, switchable to the extracted text. Anything that has no page view (or fails to open one)
 * gets the text sheet of `DocumentViewer`.
 */
export function DocumentView({ documentId, highlight, snippet, className, baseFontPx, loadContent, tryPages }: DocumentViewProps) {
  const lookForPages = tryPages ?? !loadContent
  const [mode, setMode] = useState<Mode>('page')
  const [blocks, setBlocks] = useState(false)
  const [failed, setFailed] = useState<number | null>(null)

  const { data: scan, loading } = useAsyncData(
    async (signal) => {
      if (!lookForPages) return null
      try {
        return await documentsApi.getDocumentScan(documentId, signal)
      } catch (error) {
        if (error instanceof ApiError) return null // 404: not a scan; anything else: the pages still show without blocks
        throw error
      }
    },
    [documentId, lookForPages],
  )
  // a link to a passage (?hl=) carries no text: take it from the paragraphs
  const needsText = lookForPages && !snippet && highlight !== undefined
  const { data: found } = useAsyncData(
    async (signal) => {
      if (!needsText || !highlight) return ''
      const paragraphs = await documentsApi.getDocumentContent(documentId, signal)
      return paragraphs.filter((item) => item.pi >= highlight.from && item.pi <= highlight.to).map((item) => item.text).join(' ')
    },
    [documentId, needsText, highlight?.from, highlight?.to],
  )

  const text = <DocumentViewer documentId={documentId} highlight={highlight} className={className} baseFontPx={baseFontPx} loadContent={loadContent} />
  if (!lookForPages || failed === documentId) return text
  if (loading && !scan) return <div className="viewer scan__probe"><Spinner label="Đang mở văn bản" size={24} /></div>

  const hasBlocks = (scan?.blocks.length ?? 0) > 0
  return (
    <div className="scanview">
      <div className="scanbar" role="toolbar" aria-label="Cách xem văn bản">
        <div className="scanbar__seg" role="group" aria-label="Chế độ xem">
          <button type="button" aria-pressed={mode === 'page'} className={mode === 'page' ? 'is-on' : undefined} onClick={() => setMode('page')}>Trang gốc</button>
          <button type="button" aria-pressed={mode === 'text'} className={mode === 'text' ? 'is-on' : undefined} onClick={() => setMode('text')}>Văn bản</button>
        </div>
        {mode === 'page' && hasBlocks && (
          <button type="button" className={blocks ? 'scanbar__toggle is-on' : 'scanbar__toggle'} aria-pressed={blocks} onClick={() => setBlocks((value) => !value)}>
            Hiện khối
          </button>
        )}
      </div>
      {mode === 'page' ? (
        <Suspense fallback={<div className="viewer scan__probe"><Spinner label="Đang mở văn bản" size={24} /></div>}>
          <PdfViewer
            key={documentId}
            documentId={documentId}
            scan={scan}
            highlight={highlight}
            snippet={snippet ?? found ?? undefined}
            showBlocks={blocks}
            className={className}
            onFail={() => setFailed(documentId)}
          />
        </Suspense>
      ) : text}
    </div>
  )
}
