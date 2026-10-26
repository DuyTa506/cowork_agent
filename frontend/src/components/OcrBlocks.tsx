import type { ScanBlock } from '../api'
import type { ViewerHighlight } from './DocumentViewer'

/** What OCR calls a block, in words for the person looking at the page. */
const KIND_LABELS: Record<string, string> = {
  title: 'Tiêu đề',
  header: 'Đầu trang',
  text: 'Đoạn văn',
  list: 'Danh sách',
  table: 'Bảng',
  caption: 'Chú thích',
  footnote: 'Chú giải',
  formula: 'Công thức',
  footer: 'Chân trang',
  image: 'Hình, con dấu',
  header_image: 'Hình, con dấu',
  footer_image: 'Hình, con dấu',
  page_number: 'Số trang',
}

/** Blocks drawn in the same colour: headings, running text, tables, pictures. */
const KIND_GROUP: Record<string, string> = {
  title: 'head', header: 'head', footer: 'head', page_number: 'pic',
  text: 'text', list: 'text', caption: 'text', footnote: 'text', formula: 'text',
  table: 'table', image: 'pic', header_image: 'pic', footer_image: 'pic',
}

const LINE_UNITS = 17 // height of one text line on the 0-1000 scale of a page

/** Whether the viewer paragraphs a block was written from overlap the cited range. */
export const isCited = (block: ScanBlock, highlight?: ViewerHighlight): boolean =>
  highlight !== undefined && block.pi !== null && block.pi[0] <= highlight.to && block.pi[1] >= highlight.from

interface OcrBlocksProps {
  blocks: ScanBlock[]
  highlight?: ViewerHighlight
  /** The first cited block of the document, which the viewer scrolls to. */
  firstCited?: ScanBlock
  /** Draw every block, tinted by kind (otherwise a block shows only under the pointer or when cited). */
  showAll: boolean
  /** Height / width of the page. */
  ratio: number
}

/**
 * The blocks OCR found on one page, drawn over it: each shows under the pointer (or all of them with `showAll`), a cited passage lights
 * the blocks written from it, and the text of a block sits invisibly in its box so it can be selected and found with the browser's search.
 * The parent must be a size container (`container-type: inline-size`): the text is sized in units of the page width.
 */
export function OcrBlocks({ blocks, highlight, firstCited, showAll, ratio }: OcrBlocksProps) {
  return (
    <div className={showAll ? 'scan__blocks scan__blocks--all' : 'scan__blocks'}>
      {blocks.map((block, index) => {
        const [x0, y0, x1, y1] = block.box
        const lines = Math.max(1, Math.round((y1 - y0) / LINE_UNITS))
        const cited = isCited(block, highlight)
        return (
          <div
            key={index}
            className={['scan__blk', `scan__blk--${KIND_GROUP[block.label] ?? 'text'}`, cited ? 'scan__blk--hl' : ''].filter(Boolean).join(' ')}
            data-first-hl={block === firstCited ? '' : undefined}
            title={KIND_LABELS[block.label] ?? block.label}
            style={{
              left: `${x0 / 10}%`,
              top: `${y0 / 10}%`,
              width: `${Math.max(x1 - x0, 4) / 10}%`,
              height: `${Math.max(y1 - y0, 4) / 10}%`,
              // one line of the block's height, a little smaller
              fontSize: `${(((y1 - y0) / 1000) * 100 * ratio / lines) * 0.72}cqw`,
            }}
          >
            <span className="scan__text">{block.text}</span>
          </div>
        )
      })}
    </div>
  )
}
