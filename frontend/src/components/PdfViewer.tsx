import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import 'pdfjs-dist/web/pdf_viewer.css'
import type { Scan, ScanBlock } from '../api'
import { getToken } from '../auth/tokenStorage'
import { loadPdfjs, PDFJS_OPTIONS, type PDFDocumentProxy } from '../lib/pdfjs'
import { findPassage, type TextMatch } from '../lib/pdfText'
import { Alert } from './Alert'
import { Button } from './Button'
import type { ViewerHighlight } from './DocumentViewer'
import { IconButton } from './IconButton'
import { isCited, OcrBlocks } from './OcrBlocks'
import { Spinner } from './Spinner'

const ZOOMS = [0.5, 0.75, 1, 1.25, 1.5, 2, 3]
const DEFAULT_ASPECT = 1.414 // height / width of an A4 page, until a page tells its own
const MAX_FIT_PX = 1100
const GUTTER_PX = 32
const RENDER_DELAY_MS = 150 // a drag on the drawer edge changes the width every frame: pages are redrawn when it settles
const NEAR_PX = '1200px 0px'

interface PdfViewerProps {
  documentId: number
  /** Blocks OCR found on the pages (drawn over them); null for a document that is not a scan. */
  scan: Scan | null
  highlight?: ViewerHighlight
  /** The cited passage; for a PDF with a text layer it is searched for in the pages. */
  snippet?: string
  /** Draw every OCR block, tinted by kind. */
  showBlocks: boolean
  className?: string
  /** The PDF cannot be opened (no page view for this document, or it failed); the caller shows something else. */
  onFail: (reason: string) => void
}

interface PageProps {
  pdf: PDFDocumentProxy
  number: number
  width: number
  aspect: number
  root: HTMLElement | null
  blocks: ScanBlock[]
  showBlocks: boolean
  highlight?: ViewerHighlight
  firstCited?: ScanBlock
  /** Where the cited passage is in this page's text layer, when it is. */
  match: TextMatch | null
  textLayer: boolean
  onSize: (number: number, ratio: number) => void
  onRendered: (number: number) => void
}

/** One page: drawn when it is near the screen (and dropped again when far from it), with its text layer, OCR blocks and citation. */
function PdfPage({ pdf, number, width, aspect, root, blocks, showBlocks, highlight, firstCited, match, textLayer, onSize, onRendered }: PageProps) {
  const frameRef = useRef<HTMLDivElement>(null)
  const canvasHost = useRef<HTMLDivElement>(null)
  const textHost = useRef<HTMLDivElement>(null)
  const divs = useRef<HTMLElement[]>([])
  const [near, setNear] = useState(false)
  const [own, setOwn] = useState<number | null>(null)
  const [failed, setFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [drawn, setDrawn] = useState(0)
  const [renderWidth, setRenderWidth] = useState(width)

  useEffect(() => {
    const timer = window.setTimeout(() => setRenderWidth(width), RENDER_DELAY_MS)
    return () => window.clearTimeout(timer)
  }, [width])

  useEffect(() => {
    const frame = frameRef.current
    if (!frame) return
    if (typeof IntersectionObserver === 'undefined') {
      setNear(true)
      return
    }
    const observer = new IntersectionObserver((entries) => {
      const last = entries[entries.length - 1]
      if (last) setNear(last.isIntersecting)
    }, { root, rootMargin: NEAR_PX })
    observer.observe(frame)
    return () => observer.disconnect()
  }, [root])

  useEffect(() => {
    const host = canvasHost.current
    const text = textHost.current
    if (!near) {
      host?.replaceChildren()
      text?.replaceChildren()
      divs.current = []
      return
    }
    if (!host || !text) return
    let cancelled = false
    let task: { cancel: () => void; promise: Promise<unknown> } | null = null
    let layer: { cancel: () => void } | null = null
    setFailed(false)
    void (async () => {
      try {
        const page = await pdf.getPage(number)
        const base = page.getViewport({ scale: 1 })
        const ratio = base.height / base.width
        setOwn(ratio)
        onSize(number, ratio)
        const viewport = page.getViewport({ scale: renderWidth / base.width })
        const dpr = Math.min(window.devicePixelRatio || 1, 2)
        const canvas = document.createElement('canvas')
        canvas.width = Math.floor(viewport.width * dpr)
        canvas.height = Math.floor(viewport.height * dpr)
        canvas.className = 'pdfv__canvas'
        const render = page.render({ canvas, viewport, transform: dpr === 1 ? undefined : [dpr, 0, 0, dpr, 0, 0] })
        task = render
        await render.promise
        if (cancelled) return
        host.replaceChildren(canvas)

        if (textLayer) {
          const lib = await loadPdfjs()
          const container = document.createElement('div')
          container.className = 'textLayer'
          container.style.setProperty('--total-scale-factor', String(viewport.scale))
          const made = new lib.TextLayer({ textContentSource: page.streamTextContent(), container, viewport })
          layer = made
          await made.render()
          if (cancelled) return
          text.replaceChildren(container)
          divs.current = made.textDivs
        }
        setDrawn((value) => value + 1)
        onRendered(number)
      } catch (error) {
        if (cancelled || (error instanceof Error && error.name === 'RenderingCancelledException')) return
        setFailed(true)
      }
    })()
    return () => {
      cancelled = true
      task?.cancel()
      layer?.cancel()
    }
    // onSize / onRendered are stable callbacks of the viewer
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [near, pdf, number, renderWidth, textLayer, attempt])

  // the cited passage in the text layer
  useEffect(() => {
    divs.current.forEach((div) => {
      div.classList.remove('pdfv__hl')
      div.removeAttribute('data-first-hl')
    })
    if (!match) return
    for (let index = match.from; index <= match.to; index += 1) divs.current[index]?.classList.add('pdfv__hl')
    divs.current[match.from]?.setAttribute('data-first-hl', '')
  }, [match, drawn])

  const ratio = own ?? aspect
  const style = { '--aspect': ratio, aspectRatio: `1 / ${ratio}` } as CSSProperties
  return (
    <figure className="scan__page" aria-label={`Trang ${number} trên ${pdf.numPages}`} data-page={number}>
      <div ref={frameRef} className="scan__frame" style={style}>
        <div ref={canvasHost} className="pdfv__host" />
        {textLayer && <div ref={textHost} className="pdfv__host pdfv__text" />}
        {!textLayer && <div ref={textHost} hidden />}
        {drawn === 0 && !failed && <div className="scan__wait"><Spinner size={22} label={`Đang vẽ trang ${number}`} /></div>}
        {failed && (
          <div className="scan__wait scan__wait--err" role="alert">
            <span>Không vẽ được trang {number}.</span>
            <Button size="sm" icon="refresh" onClick={() => setAttempt((value) => value + 1)}>Thử lại</Button>
          </div>
        )}
        {drawn > 0 && blocks.length > 0 && <OcrBlocks blocks={blocks} highlight={highlight} firstCited={firstCited} showAll={showBlocks} ratio={ratio} />}
      </div>
      <figcaption className="scan__no">Trang {number} / {pdf.numPages}</figcaption>
    </figure>
  )
}

/**
 * A document as its own pages, drawn in the browser by pdf.js from the PDF the server gives (the original, or the one made from a Word
 * file) so fonts, tables and layout are those of the document. Only the pages near the screen are fetched (HTTP ranges) and drawn.
 * OCR blocks of a scan are drawn over the pages; a cited passage is lit, by block for a scan and by text search for other PDFs.
 */
export function PdfViewer({ documentId, scan, highlight, snippet, showBlocks, className, onFail }: PdfViewerProps) {
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null)
  const [aspect, setAspect] = useState(DEFAULT_ASPECT)
  const [zoom, setZoom] = useState(1)
  const [available, setAvailable] = useState(0)
  const [scroller, setScroller] = useState<HTMLDivElement | null>(null)
  const [current, setCurrent] = useState(1)
  const [match, setMatch] = useState<{ page: number; at: TextMatch } | null>(null)
  const [searched, setSearched] = useState(false)
  const [rendered, setRendered] = useState<ReadonlySet<number>>(new Set())
  const sheetRef = useRef<HTMLDivElement>(null)
  const sized = useRef(false)
  const scrolledFor = useRef('')
  const failRef = useRef(onFail)
  useEffect(() => {
    failRef.current = onFail
  })

  const blocks = scan?.blocks
  const byPage = useMemo(() => {
    const map = new Map<number, ScanBlock[]>()
    for (const block of blocks ?? []) map.set(block.page, [...(map.get(block.page) ?? []), block])
    return map
  }, [blocks])
  const hasBlocks = byPage.size > 0
  const firstCited = useMemo(() => blocks?.find((block) => isCited(block, highlight)), [blocks, highlight])

  // open the PDF
  useEffect(() => {
    let cancelled = false
    let task: { destroy: () => Promise<void> } | null = null
    sized.current = false
    setPdf(null)
    setMatch(null)
    setSearched(false)
    setRendered(new Set())
    void (async () => {
      try {
        const lib = await loadPdfjs()
        if (cancelled) return
        const token = getToken()
        const loading = lib.getDocument({
          url: `/api/documents/${documentId}/preview`,
          httpHeaders: token ? { Authorization: `Bearer ${token}` } : {},
          rangeChunkSize: 1 << 18,
          ...PDFJS_OPTIONS,
        })
        task = loading
        const opened = await loading.promise
        if (cancelled) return
        setPdf(opened)
      } catch (error) {
        if (cancelled) return
        failRef.current(error instanceof Error ? error.message : 'Không mở được bản xem trang.')
      }
    })()
    return () => {
      cancelled = true
      void task?.destroy() // also closes the document it opened
    }
  }, [documentId])

  // follow the width of the pane
  useEffect(() => {
    if (!scroller) return
    const measure = () => setAvailable(scroller.clientWidth)
    measure()
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(measure)
    observer.observe(scroller)
    return () => observer.disconnect()
  }, [scroller])
  const fit = Math.max(240, Math.min(MAX_FIT_PX, available - GUTTER_PX))
  const width = Math.round(fit * zoom)

  const onSize = useCallback((_number: number, ratio: number) => {
    if (sized.current) return
    sized.current = true
    setAspect(ratio)
  }, [])
  const onRendered = useCallback((number: number) => setRendered((current) => (current.has(number) ? current : new Set(current).add(number))), [])

  // find a cited passage in the text layer of a PDF that is not a scan
  const text = useMemo(() => (snippet ?? '').trim(), [snippet])
  useEffect(() => {
    if (!pdf || hasBlocks || text.length < 12) return
    let cancelled = false
    void (async () => {
      for (let number = 1; number <= pdf.numPages && !cancelled; number += 1) {
        try {
          const page = await pdf.getPage(number)
          const content = await page.getTextContent()
          const items = content.items.flatMap((item) => ('str' in item ? [item.str] : []))
          const found = findPassage(items, text)
          if (cancelled) return
          if (found) {
            setMatch({ page: number, at: found })
            return
          }
        } catch {
          return
        }
      }
      if (!cancelled) setSearched(true)
    })()
    return () => {
      cancelled = true
    }
  }, [pdf, hasBlocks, text])

  const target = hasBlocks ? firstCited?.page : match?.page
  const targetKey = hasBlocks ? `b${highlight?.from}-${highlight?.to}` : `t${match?.page}:${match?.at.from}`
  const jumped = useRef('')
  // jump to the page of the citation, then centre the lit passage once that page is drawn
  useEffect(() => {
    if (!target || !scroller || !pdf) return
    const frame = sheetRef.current?.querySelector<HTMLElement>(`[data-page="${target}"]`)
    if (!frame) return
    if (jumped.current !== targetKey) {
      jumped.current = targetKey
      scroller.scrollTop += frame.getBoundingClientRect().top - scroller.getBoundingClientRect().top - 12
    }
  }, [target, targetKey, scroller, pdf, width])
  useEffect(() => {
    if (!target || !scroller || !rendered.has(target) || scrolledFor.current === targetKey) return
    const lit = sheetRef.current?.querySelector<HTMLElement>('[data-first-hl]')
    if (!lit) return
    scrolledFor.current = targetKey
    const box = lit.getBoundingClientRect()
    scroller.scrollTop += box.top - scroller.getBoundingClientRect().top - (scroller.clientHeight - box.height) / 2
  }, [target, targetKey, scroller, rendered])
  useEffect(() => {
    scrolledFor.current = ''
    jumped.current = ''
  }, [documentId])

  // the page being read, for the indicator
  useEffect(() => {
    if (!scroller) return
    let frame = 0
    const update = () => {
      frame = 0
      const top = scroller.getBoundingClientRect().top + scroller.clientHeight * 0.35
      let page = 1
      for (const figure of sheetRef.current?.children ?? []) {
        if (figure.getBoundingClientRect().top > top) break
        page = Number((figure as HTMLElement).dataset.page) || page
      }
      setCurrent(page)
    }
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(update)
    }
    scroller.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      scroller.removeEventListener('scroll', onScroll)
      if (frame) cancelAnimationFrame(frame)
    }
  }, [scroller])

  const step = (direction: 1 | -1) => {
    const next = direction === 1 ? ZOOMS.find((value) => value > zoom) : [...ZOOMS].reverse().find((value) => value < zoom)
    if (next !== undefined) setZoom(next)
  }
  const pages = pdf ? Array.from({ length: pdf.numPages }, (_, index) => index + 1) : []
  const sheetStyle: CSSProperties = { width }

  return (
    <div className={['viewer', 'scan', 'pdfv', className].filter(Boolean).join(' ')}>
      <div ref={setScroller} className="viewer__scroll scan__scroll" tabIndex={0} aria-label="Các trang của văn bản">
        {!pdf && <div className="viewer__status"><Spinner label="Đang mở văn bản" size={24} /></div>}
        {pdf && pdf.numPages === 0 && <Alert kind="info" title="Văn bản không có trang để hiển thị" />}
        {pdf && searched && highlight && (
          <p className="pdfv__note" role="status">Chưa tìm thấy đoạn được trích dẫn trên các trang này; chuyển sang “Văn bản” để xem đoạn đó.</p>
        )}
        <div ref={sheetRef} className="scan__sheet" style={sheetStyle}>
          {pdf && pages.map((number) => (
            <PdfPage
              key={number}
              pdf={pdf}
              number={number}
              width={width}
              aspect={aspect}
              root={scroller}
              blocks={byPage.get(number) ?? []}
              showBlocks={showBlocks}
              highlight={highlight}
              firstCited={firstCited}
              match={match?.page === number ? match.at : null}
              textLayer={!hasBlocks}
              onSize={onSize}
              onRendered={onRendered}
            />
          ))}
        </div>
      </div>
      {pdf && (
        <div className="viewer__zoom" role="group" aria-label="Thu phóng">
          <IconButton icon="zoomOut" label="Thu nhỏ" size={18} onClick={() => step(-1)} disabled={zoom <= (ZOOMS[0] ?? 0.5)} />
          <span className="viewer__zoom-value" aria-live="polite">{zoom === 1 ? 'Vừa khít' : `${Math.round(zoom * 100)}%`}</span>
          <IconButton icon="zoomIn" label="Phóng to" size={18} onClick={() => step(1)} disabled={zoom >= (ZOOMS[ZOOMS.length - 1] ?? 3)} />
          <span className="viewer__zoom-sep" aria-hidden="true" />
          <IconButton icon="fit" label="Vừa chiều rộng" size={18} aria-pressed={zoom === 1} className={zoom === 1 ? 'is-on' : undefined} onClick={() => setZoom(1)} />
          <span className="viewer__zoom-sep" aria-hidden="true" />
          <span className="viewer__zoom-value tnum" aria-live="polite">{current} / {pdf.numPages}</span>
        </div>
      )}
    </div>
  )
}
