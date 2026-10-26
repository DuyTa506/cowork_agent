import type { KeyboardEvent } from 'react'
import type { DocumentSummary } from '../../api'
import { isYearTag } from '../../lib/documentFilters'
import { documentSymbol, documentNote } from '../../lib/documents'
import { formatDate } from '../../lib/format'
import { LevelChip, StateChip } from '../Chip'
import { FileTypeBadge } from '../FileTypeBadge'
import { RowMenu, type MenuAction } from './RowMenu'
import { TagChips } from './TagChips'

export interface RowActions {
  onOpen: (document: DocumentSummary) => void
  onOpenPage: (document: DocumentSummary) => void
  onDownload: (document: DocumentSummary) => void
  onReprocess: (document: DocumentSummary) => void
  onDelete: (document: DocumentSummary) => void
  canManage: (document: DocumentSummary) => boolean
  /** A tag chip in a row was clicked: filter by it. */
  onPickTag: (tag: string) => void
}

interface DocumentTableProps {
  /** null while loading: shows skeleton rows. */
  documents: DocumentSummary[] | null
  selectedId: number | null
  /** Tags in force as a filter, drawn as pressed on the rows. */
  activeTags?: readonly string[]
  onSelect: (document: DocumentSummary) => void
  actions: RowActions
}

const SKELETON_ROWS = 8

/** States whose note (reason, missing info) is worth a line under the chip. */
function noteFor(document: DocumentSummary): string {
  if (document.state === 'needs_review' || document.state === 'needs_ocr' || document.state === 'failed') return documentNote(document)
  if (document.state === 'processing') return document.state_detail
  return ''
}

/** The document list: sticky header, 56 px rows with file-type badge, title, unit, date, level and a large state chip. */
export function DocumentTable({ documents, selectedId, activeTags, onSelect, actions }: DocumentTableProps) {
  const onRowKey = (event: KeyboardEvent<HTMLTableRowElement>, document: DocumentSummary) => {
    if (event.target !== event.currentTarget) return
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      onSelect(document)
    } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      const sibling = event.key === 'ArrowDown' ? event.currentTarget.nextElementSibling : event.currentTarget.previousElementSibling
      if (sibling instanceof HTMLElement) sibling.focus()
    }
  }

  return (
    <table className="dtable">
      <caption className="sr-only">Danh sách văn bản</caption>
      <colgroup>
        <col />
        <col className="dtable__c-unit" />
        <col className="dtable__c-date" />
        <col className="dtable__c-level" />
        <col className="dtable__c-state" />
        <col className="dtable__c-act" />
      </colgroup>
      <thead>
        <tr>
          <th scope="col">Văn bản</th>
          <th scope="col" className="dtable__unit">Đơn vị</th>
          <th scope="col" className="dtable__date">Ngày ban hành</th>
          <th scope="col" className="dtable__level">Mức độ</th>
          <th scope="col">Trạng thái</th>
          <th scope="col"><span className="sr-only">Thao tác</span></th>
        </tr>
      </thead>
      <tbody aria-busy={documents === null || undefined}>
        {documents === null &&
          Array.from({ length: SKELETON_ROWS }, (_, index) => (
            <tr key={index} className="dtable__skeleton" aria-hidden="true">
              <td>
                <div className="dtable__file">
                  <span className="skeleton skeleton--badge" />
                  <div className="dtable__text">
                    <span className="skeleton skeleton--line" style={{ width: `${62 - (index % 3) * 12}%` }} />
                    <span className="skeleton skeleton--line skeleton--short" />
                  </div>
                </div>
              </td>
              <td className="dtable__unit"><span className="skeleton skeleton--line" style={{ width: '70%' }} /></td>
              <td className="dtable__date"><span className="skeleton skeleton--line" style={{ width: 78 }} /></td>
              <td className="dtable__level"><span className="skeleton skeleton--chip" /></td>
              <td><span className="skeleton skeleton--chip skeleton--chip-wide" /></td>
              <td />
            </tr>
          ))}
        {documents?.map((document) => {
          const selected = document.id === selectedId
          const hasTitle = Boolean((document.subject || document.title).trim())
          const hasIdentity = Boolean(document.document_number || document.symbol)
          const meta = [hasIdentity ? documentSymbol(document) : null, !hasTitle ? document.original_name : null, document.document_type || (hasIdentity ? null : 'Chưa nhận dạng loại')].filter(Boolean)
          const note = noteFor(document)
          const manage = actions.canManage(document)
          const menu: MenuAction[] = [
            { key: 'open', label: 'Xem chi tiết', icon: 'eye', onSelect: () => actions.onOpen(document) },
            { key: 'page', label: 'Mở trang riêng', icon: 'expand', onSelect: () => actions.onOpenPage(document) },
            { key: 'download', label: 'Tải tệp gốc', icon: 'download', onSelect: () => actions.onDownload(document) },
          ]
          if (manage) {
            if (document.state !== 'uploaded' && document.state !== 'processing') {
              menu.push({ key: 'reprocess', label: 'Xử lý lại', icon: 'refresh', separated: true, onSelect: () => actions.onReprocess(document) })
            }
            menu.push({ key: 'delete', label: 'Xóa văn bản', icon: 'trash', danger: true, separated: document.state === 'uploaded' || document.state === 'processing', onSelect: () => actions.onDelete(document) })
          }
          return (
            <tr
              key={document.id}
              data-doc-id={document.id}
              className={selected ? 'is-selected' : undefined}
              aria-current={selected || undefined}
              tabIndex={0}
              onClick={() => onSelect(document)}
              onKeyDown={(event) => onRowKey(event, document)}
            >
              <td>
                <div className="dtable__file">
                  <FileTypeBadge name={document.original_name} size="md" />
                  <div className="dtable__text">
                    <div className={hasTitle ? 'dtable__title' : 'dtable__title dtable__title--empty'}>
                      {hasTitle ? document.subject || document.title : 'Chưa trích xuất được trích yếu'}
                    </div>
                    <div className="dtable__meta tnum">
                      {meta.join(' · ')}
                      <span className="dtable__inline">{[document.unit_name || document.unit_id, document.issued_date ? formatDate(document.issued_date) : ''].filter(Boolean).map((part) => ` · ${part}`).join('')}</span>
                    </div>
                    <TagChips tags={document.tags.filter((tag) => !isYearTag(tag))} active={activeTags} onPick={actions.onPickTag} />
                  </div>
                </div>
              </td>
              <td className="dtable__unit"><span className="dtable__clamp">{document.unit_name || document.unit_id}</span></td>
              <td className="dtable__date tnum">{document.issued_date ? formatDate(document.issued_date) : <span className="muted">—</span>}</td>
              <td className="dtable__level"><LevelChip level={document.level} /></td>
              <td>
                <StateChip state={document.state} />
                {note && <div className="dtable__note" title={note}>{note}</div>}
              </td>
              <td className="dtable__act"><RowMenu label={`Thao tác: ${hasTitle ? document.subject || document.title : document.original_name}`} actions={menu} /></td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
