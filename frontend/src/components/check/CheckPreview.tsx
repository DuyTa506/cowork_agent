import { useEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent, type ReactNode } from 'react'
import type { CheckItem, CheckPara } from '../../api/formatCheck'
import { Icon } from '../Icon'
import { Select } from '../Select'
import { Spinner } from '../Spinner'
import { LEVELS, type FormatLevel } from './model'

interface CheckPreviewProps {
  paras: CheckPara[]
  /** Worst format severity per paragraph `pi`. */
  levels: Map<number, FormatLevel>
  items: Map<string, CheckItem>
  /** Paragraph to scroll to and emphasise. */
  activePi: number | null
  /** Bumps when the same paragraph is asked for again. */
  activeNonce: number
  /** Page numbers are estimates (Word) rather than real (PDF). */
  estimatedPages: boolean
  onSelectPara: (pi: number) => void
  /** Small print under the sheet. */
  footNote: string
  /** A new check is running. */
  busy?: boolean
  /** Spelling screen: a misspelt word is a button that asks the list for its row (`itemId` is null for a word with no suggestion). */
  onSelectMark?: (itemId: string | null, pi: number) => void
  /** Item id of the word to emphasise. */
  activeMark?: string | null
  /** Legend entries shown under the title; the format screen's by default. */
  legend?: 'format' | 'spelling'
}

interface Cell {
  col: number
  paras: CheckPara[]
}

type Block = { kind: 'para'; para: CheckPara } | { kind: 'table'; rows: Cell[][]; columns: number }

/** Groups consecutive paragraphs of the same table into rows and cells. */
function buildBlocks(paras: CheckPara[]): Block[] {
  const blocks: Block[] = []
  let index = 0
  while (index < paras.length) {
    const para = paras[index]
    if (!para) break
    if (para.table === null) {
      blocks.push({ kind: 'para', para })
      index += 1
      continue
    }
    const tableId = para.table
    const rows = new Map<number, Map<number, CheckPara[]>>()
    while (index < paras.length && paras[index]?.table === tableId) {
      const cell = paras[index] as CheckPara
      const row = rows.get(cell.row ?? 0) ?? new Map<number, CheckPara[]>()
      row.set(cell.col ?? 0, [...(row.get(cell.col ?? 0) ?? []), cell])
      rows.set(cell.row ?? 0, row)
      index += 1
    }
    const ordered = [...rows.entries()].sort(([a], [b]) => a - b).map(([, cells]) =>
      [...cells.entries()].sort(([a], [b]) => a - b).map(([col, group]) => ({ col, paras: group })),
    )
    blocks.push({ kind: 'table', rows: ordered, columns: Math.max(...ordered.map((cells) => (cells.at(-1)?.col ?? 0) + 1)) })
  }
  return blocks
}

const ZOOMS = [0.5, 0.75, 1, 1.25, 1.5, 2]
const BASE_FONT_PX = 13.5
const BASE_WIDTH_PX = 640

function alignOf(align: string): CSSProperties['textAlign'] {
  if (align === 'center' || align === 'right') return align
  return align === 'both' || align === 'justify' || align === 'distribute' ? 'justify' : 'left'
}

const pageOf = (para: CheckPara): number | null => para.page ?? para.pg

const ZOOM_OPTIONS = [
  { value: 'fit', label: 'Vừa chiều rộng' },
  ...ZOOMS.map((value) => ({ value: String(value), label: `${Math.round(value * 100)}%` })),
]

/**
 * The document as a white sheet. A paragraph with a format finding gets a coloured bar, a pale tint and a small glyph in the margin
 * (shape, not only colour, tells the severity); misspelt words are underlined with a wave. Clicking a marked paragraph asks the list
 * to show its finding.
 */
export function CheckPreview({ paras, levels, items, activePi, activeNonce, estimatedPages, onSelectPara, footNote, busy, onSelectMark, activeMark, legend = 'format' }: CheckPreviewProps) {
  const [zoom, setZoom] = useState<'fit' | number>('fit')
  const sheetRef = useRef<HTMLDivElement>(null)
  const blocks = useMemo(() => buildBlocks(paras), [paras])
  const pages = useMemo(() => new Set(paras.map(pageOf).filter((page): page is number => page !== null)), [paras])

  useEffect(() => {
    if (activePi === null) return
    sheetRef.current?.querySelector(`[data-pi="${activePi}"]`)?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [activePi, activeNonce])

  const step = (direction: 1 | -1) => {
    const current = zoom === 'fit' ? 1 : zoom
    const next = direction === 1 ? ZOOMS.find((value) => value > current) : [...ZOOMS].reverse().find((value) => value < current)
    if (next !== undefined) setZoom(next)
  }
  const scale = zoom === 'fit' ? 1 : zoom
  const sheetStyle: CSSProperties = { fontSize: BASE_FONT_PX * scale, width: zoom === 'fit' ? undefined : BASE_WIDTH_PX * scale }

  /** Text with its misspelt words underlined. */
  const renderText = (para: CheckPara): ReactNode => {
    if (para.blank || para.text === '') return ' '
    const parts: ReactNode[] = []
    let cursor = 0
    for (const [start, end, itemId] of [...para.marks].sort((a, b) => a[0] - b[0])) {
      if (start < cursor || end <= start || end > para.text.length) continue // overlapping or out of range: keep the first
      if (start > cursor) parts.push(para.text.slice(cursor, start))
      const suggestion = itemId ? items.get(itemId)?.raw_after : undefined
      const title = suggestion ? `Có thể sai chính tả. Gợi ý: ${suggestion}` : 'Có thể sai chính tả'
      const classes = ['check-misspell', onSelectMark && 'check-misspell--link', itemId && itemId === activeMark && 'check-misspell--active'].filter(Boolean).join(' ')
      parts.push(
        onSelectMark ? (
          <span
            key={`${start}-${end}`}
            className={classes}
            title={title}
            role="button"
            tabIndex={0}
            onClick={(event) => { event.stopPropagation(); onSelectMark(itemId, para.pi) }}
            onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelectMark(itemId, para.pi) } }}
          >
            {para.text.slice(start, end)}
          </span>
        ) : (
          <span key={`${start}-${end}`} className="check-misspell" title={title}>
            {para.text.slice(start, end)}
          </span>
        ),
      )
      cursor = end
    }
    if (cursor === 0) return para.text
    if (cursor < para.text.length) parts.push(para.text.slice(cursor))
    return parts
  }

  const renderPara = (para: CheckPara) => {
    const level = levels.get(para.pi) ?? (para.msgs.length > 0 ? 'warning' : undefined)
    const classes = [
      'check-p',
      level && `check-p--${level}`,
      activePi === para.pi && 'check-p--active',
    ].filter(Boolean).join(' ')
    const open = () => onSelectPara(para.pi)
    const onKeyDown = (event: KeyboardEvent<HTMLParagraphElement>) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault()
        open()
      }
    }
    return (
      <p
        key={para.pi}
        data-pi={para.pi}
        className={classes}
        style={{ textAlign: alignOf(para.align), fontWeight: para.bold ? 700 : undefined }}
        tabIndex={level ? 0 : undefined}
        onClick={level ? open : undefined}
        onKeyDown={level ? onKeyDown : undefined}
      >
        {level && para.where !== 'cell' && (
          <span className={`check-flag check-flag--${level}`} aria-hidden="true"><Icon name={LEVELS[level].icon} size={14} weight="fill" /></span>
        )}
        {renderText(para)}
        {para.msgs.length > 0 && <span className="sr-only"> Lỗi thể thức: {para.msgs.join(' ')}</span>}
      </p>
    )
  }

  let lastPage: number | null = null
  const withPageMark = (key: string, page: number | null, content: ReactNode): ReactNode => {
    const mark = pages.size > 1 && page !== null && page !== lastPage
    if (page !== null) lastPage = page
    return (
      <div key={key} className="check-page-block">
        {mark && <div className="check-pagebreak"><span>Trang {page}{estimatedPages ? ' (ước tính)' : ''}</span></div>}
        {content}
      </div>
    )
  }

  const stepper = (label: string, icon: 'minus' | 'plus', direction: 1 | -1) => (
    <button type="button" className="check-tool" aria-label={label} title={label} onClick={() => step(direction)}>
      <Icon name={icon} size={16} />
    </button>
  )

  return (
    <>
      <div className="check-pv__head">
        <Icon name="fileSearch" size={20} />
        <h2 className="check-pv__title">Xem trước</h2>
        {busy && <Spinner label="Đang kiểm tra lại" />}
        <div className="check-pv__zoom" role="group" aria-label="Thu phóng">
          {stepper('Thu nhỏ', 'minus', -1)}
          <Select
            aria-label="Mức thu phóng"
            className="check-pv__zoomsel"
            value={String(zoom)}
            options={ZOOM_OPTIONS}
            onChange={(value) => setZoom(value === 'fit' ? 'fit' : Number(value))}
          />
          {stepper('Phóng to', 'plus', 1)}
        </div>
      </div>
      <ul className="check-legend" aria-label="Chú giải">
        {legend === 'format' && (
          <>
            <li><span className="check-flag check-flag--error"><Icon name={LEVELS.error.icon} size={14} weight="fill" /></span>Bắt buộc</li>
            <li><span className="check-flag check-flag--warning"><Icon name={LEVELS.warning.icon} size={14} weight="fill" /></span>Cảnh báo</li>
            <li><span className="check-flag check-flag--info"><Icon name={LEVELS.info.icon} size={14} weight="fill" /></span>Lưu ý</li>
          </>
        )}
        <li><span className="check-misspell">{legend === 'spelling' ? 'Từ nghi sai (bấm để xem gợi ý)' : 'Chính tả'}</span></li>
      </ul>
      <div className="check-sheet">
        <div className="check-sheet__scroll">
          <div ref={sheetRef} className={zoom === 'fit' ? 'check-paper check-paper--fit' : 'check-paper'} style={sheetStyle}>
            {blocks.length === 0 && <p className="check-paper__empty">Văn bản không có nội dung để hiển thị.</p>}
            {blocks.map((block, blockIndex) => {
              if (block.kind === 'para') return withPageMark(`p${block.para.pi}`, pageOf(block.para), renderPara(block.para))
              const first = block.rows[0]?.[0]?.paras[0]
              return withPageMark(
                `t${blockIndex}`,
                first ? pageOf(first) : null,
                <table className="check-paper__table">
                  <tbody>
                    {block.rows.map((cells, rowIndex) => (
                      <tr key={rowIndex}>
                        {Array.from({ length: block.columns }, (_, col) => (
                          <td key={col}>{cells.find((candidate) => candidate.col === col)?.paras.map(renderPara)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>,
              )
            })}
          </div>
        </div>
      </div>
      <p className="check-pv__foot">{footNote}</p>
    </>
  )
}
