import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { documentsApi, type Paragraph } from '../api'
import { useAsyncData } from '../hooks/useAsyncData'
import { Alert } from './Alert'
import { IconButton } from './IconButton'
import { Spinner } from './Spinner'

/** Range of paragraph indexes (`pi`, inclusive) to highlight, for example a cited passage. */
export interface ViewerHighlight {
  from: number
  to: number
}

interface DocumentViewerProps {
  documentId: number
  highlight?: ViewerHighlight
  className?: string
  /** Text size at 100 % (default 13.5 px; the full-page view uses a larger sheet). */
  baseFontPx?: number
  /** Loads the paragraphs from somewhere other than the document store (for example a chat attachment). Remount (`key`) to change source. */
  loadContent?: (signal: AbortSignal) => Promise<Paragraph[]>
}

interface TableCell {
  col: number
  paragraphs: Paragraph[]
}

type Block =
  | { kind: 'paragraph'; paragraph: Paragraph }
  | { kind: 'table'; rows: TableCell[][]; columns: number }

/** Groups consecutive table paragraphs (same `table`) into rows and cells; other paragraphs stay as they are. */
function buildBlocks(paragraphs: Paragraph[]): Block[] {
  const blocks: Block[] = []
  let index = 0
  while (index < paragraphs.length) {
    const paragraph = paragraphs[index]
    if (!paragraph) break
    if (paragraph.table === null) {
      blocks.push({ kind: 'paragraph', paragraph })
      index += 1
      continue
    }
    const tableId = paragraph.table
    const rows = new Map<number, Map<number, Paragraph[]>>()
    while (index < paragraphs.length && paragraphs[index]?.table === tableId) {
      const cell = paragraphs[index] as Paragraph
      const row = rows.get(cell.row ?? 0) ?? new Map<number, Paragraph[]>()
      row.set(cell.col ?? 0, [...(row.get(cell.col ?? 0) ?? []), cell])
      rows.set(cell.row ?? 0, row)
      index += 1
    }
    const ordered = [...rows.entries()].sort(([a], [b]) => a - b).map(([, cells]) => (
      [...cells.entries()].sort(([a], [b]) => a - b).map(([col, items]) => ({ col, paragraphs: items }))
    ))
    const columns = Math.max(...ordered.map((cells) => (cells.at(-1)?.col ?? 0) + 1))
    blocks.push({ kind: 'table', rows: ordered, columns })
  }
  return blocks
}

const ZOOMS = [0.5, 0.75, 1, 1.25, 1.5, 2]
const BASE_FONT_PX = 13.5
const BASE_WIDTH_PX = 640

/**
 * Renders a document's text from GET /api/documents/{id}/content as a white sheet of paper on a grey-blue desk.
 * Paragraphs carry `data-pi` so a citation can be located; the `highlight` range is marked (tinted, with a brass bar) and
 * scrolled into view. Zoom is "fit width" (the sheet follows its container) or a fixed percentage.
 */
export function DocumentViewer({ documentId, highlight, className, loadContent, baseFontPx = BASE_FONT_PX }: DocumentViewerProps) {
  const { data, error, loading } = useAsyncData(
    (signal) => (loadContent ? loadContent(signal) : documentsApi.getDocumentContent(documentId, signal)),
    [documentId],
  )
  const [zoom, setZoom] = useState<'fit' | number>('fit')
  const sheetRef = useRef<HTMLDivElement>(null)
  const blocks = useMemo(() => (data ? buildBlocks(data) : []), [data])

  useEffect(() => {
    if (!highlight || blocks.length === 0) return
    sheetRef.current?.querySelector('.viewer__hl')?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [highlight, blocks])

  const isMarked = (pi: number) => highlight !== undefined && pi >= highlight.from && pi <= highlight.to

  const step = (direction: 1 | -1) => {
    const current = zoom === 'fit' ? 1 : zoom
    const next = direction === 1 ? ZOOMS.find((value) => value > current) : [...ZOOMS].reverse().find((value) => value < current)
    if (next !== undefined) setZoom(next)
  }

  const scale = zoom === 'fit' ? 1 : zoom
  const sheetStyle: CSSProperties = {
    fontSize: baseFontPx * scale,
    width: zoom === 'fit' ? undefined : (BASE_WIDTH_PX * baseFontPx / BASE_FONT_PX) * scale,
  }

  const renderParagraph = (paragraph: Paragraph) => (
    <p
      key={paragraph.pi}
      data-pi={paragraph.pi}
      className={isMarked(paragraph.pi) ? 'viewer__hl' : undefined}
      style={{
        textAlign: paragraph.align === 'justify' || paragraph.align === 'center' || paragraph.align === 'right' ? paragraph.align : 'left',
        fontWeight: paragraph.bold ? 700 : undefined,
        fontStyle: paragraph.italic ? 'italic' : undefined,
      }}
    >
      {paragraph.text}
    </p>
  )

  return (
    <div className={['viewer', className].filter(Boolean).join(' ')}>
      <div className="viewer__scroll" tabIndex={0} aria-label="Nội dung văn bản">
        {loading && !data && <div className="viewer__status"><Spinner label="Đang tải nội dung văn bản" size={24} /></div>}
        {error && <Alert kind="error" title="Không hiển thị được nội dung văn bản">{error.message}</Alert>}
        {data && (
          <div ref={sheetRef} className={zoom === 'fit' ? 'viewer__sheet viewer__sheet--fit' : 'viewer__sheet'} style={sheetStyle}>
            {blocks.length === 0 && <p className="viewer__empty">Văn bản không có nội dung để hiển thị.</p>}
            {blocks.map((block, blockIndex) =>
              block.kind === 'paragraph' ? (
                renderParagraph(block.paragraph)
              ) : (
                <table key={`table-${blockIndex}`} className="viewer__table">
                  <tbody>
                    {block.rows.map((cells, rowIndex) => (
                      <tr key={rowIndex}>
                        {Array.from({ length: block.columns }, (_, col) => {
                          const cell = cells.find((candidate) => candidate.col === col)
                          return <td key={col}>{cell?.paragraphs.map(renderParagraph)}</td>
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              ),
            )}
          </div>
        )}
      </div>
      {data && (
        <div className="viewer__zoom" role="group" aria-label="Thu phóng">
          <IconButton icon="zoomOut" label="Thu nhỏ" size={18} onClick={() => step(-1)} disabled={scale <= (ZOOMS[0] ?? 0.5)} />
          <span className="viewer__zoom-value" aria-live="polite">{zoom === 'fit' ? 'Vừa khít' : `${Math.round(zoom * 100)}%`}</span>
          <IconButton icon="zoomIn" label="Phóng to" size={18} onClick={() => step(1)} disabled={scale >= (ZOOMS[ZOOMS.length - 1] ?? 2)} />
          <span className="viewer__zoom-sep" aria-hidden="true" />
          <IconButton
            icon="fit"
            label="Vừa chiều rộng"
            size={18}
            aria-pressed={zoom === 'fit'}
            className={zoom === 'fit' ? 'is-on' : undefined}
            onClick={() => setZoom('fit')}
          />
        </div>
      )}
    </div>
  )
}
