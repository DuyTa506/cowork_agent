import { useEffect, useState } from 'react'
import { ApiError, documentsApi, type DocumentDetail } from '../../api'
import { useAsyncData } from '../../hooks/useAsyncData'
import { documentSymbol, documentTitle, downloadOriginal, isInProgress } from '../../lib/documents'
import { formatDate, formatDateTime, formatFileSize, formatNumber } from '../../lib/format'
import { Alert } from '../Alert'
import { Button } from '../Button'
import { LevelChip, StateChip } from '../Chip'
import { ConfirmDialog } from '../ConfirmDialog'
import { DocumentView } from '../DocumentView'
import { EmptyState } from '../EmptyState'
import { FileTypeBadge } from '../FileTypeBadge'
import { IconButton } from '../IconButton'
import { Spinner } from '../Spinner'
import { useToast } from '../Toast'
import { Callout } from './Callout'
import { DetailTabs } from './DetailTabs'
import { MetadataForm, ReadRow } from './MetadataForm'
import { ProcessingSteps } from './ProcessingSteps'
import { TagEditor } from './TagEditor'

type TabKey = 'preview' | 'info' | 'progress'

const TAB_LABELS: Record<TabKey, string> = { preview: 'Xem trước', info: 'Thông tin', progress: 'Tiến trình' }

interface DocumentDetailPanelProps {
  documentId: number
  /** `drawer`: the list page's side drawer (preview tab first); `page`: the info column of /kho/:id (the paper is beside it). */
  variant?: 'drawer' | 'page'
  /** Shows a close button (the drawer). */
  onClose?: () => void
  /** Shows "Mở trang riêng" (the drawer). */
  onOpenPage?: () => void
  /** Called after the document was changed (saved, reprocessed) so the list can refresh. */
  onChanged?: () => void
  /** Called after the document was deleted. */
  onDeleted?: () => void
  /** Called with the loaded document (the page uses it for the breadcrumb). */
  onLoaded?: (document: DocumentDetail) => void
  /** Tags already used in the store, offered while typing a new one. */
  tagSuggestions?: string[]
}

/**
 * Detail of one document: header (type badge, title, state and level chips), tabs (Xem trước · Thông tin · Tiến trình)
 * and a sticky footer with the actions. Refreshes itself while the document is being processed.
 */
export function DocumentDetailPanel({ documentId, variant = 'drawer', onClose, onOpenPage, onChanged, onDeleted, onLoaded, tagSuggestions = [] }: DocumentDetailPanelProps) {
  const notify = useToast()
  const tabs: TabKey[] = variant === 'drawer' ? ['preview', 'info', 'progress'] : ['info', 'progress']
  const [tab, setTab] = useState<TabKey>(tabs[0] ?? 'info')
  const { data, error, loading, reload, setData } = useAsyncData(
    (signal) => documentsApi.getDocument(documentId, signal),
    [documentId],
    { pollMs: 3000, shouldPoll: isInProgress },
  )
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [reprocessing, setReprocessing] = useState(false)
  const [downloading, setDownloading] = useState(false)

  useEffect(() => {
    if (data) onLoaded?.(data)
    // `onLoaded` is the parent's setter; only a new document should re-notify it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data])

  const changed = (document: DocumentDetail) => {
    setData(document)
    if (isInProgress(document)) reload() // restarts the background refresh
    onChanged?.()
  }

  const download = async (document: DocumentDetail) => {
    setDownloading(true)
    try {
      await downloadOriginal(document)
    } catch (failure) {
      notify(failure instanceof Error ? failure.message : 'Không tải được tệp gốc.', 'error')
    } finally {
      setDownloading(false)
    }
  }

  const reprocess = async (document: DocumentDetail) => {
    setReprocessing(true)
    try {
      changed(await documentsApi.reprocessDocument(document.id))
      notify('Đã đưa văn bản vào hàng đợi xử lý lại.')
    } catch (failure) {
      notify(failure instanceof Error ? failure.message : 'Không xử lý lại được.', 'error')
    } finally {
      setReprocessing(false)
    }
  }

  const remove = async (document: DocumentDetail) => {
    await documentsApi.deleteDocument(document.id)
    notify('Đã xóa văn bản.')
    setConfirmDelete(false)
    onDeleted?.()
  }

  const closeButton = onClose && <IconButton icon="close" label="Đóng chi tiết" size={20} onClick={onClose} />

  if (error && !data) {
    const gone = error instanceof ApiError && error.status === 404
    return (
      <div className={`dpanel dpanel--${variant}`}>
        <header className="dpanel__head dpanel__head--plain">
          <h2 className="dpanel__title">Chi tiết văn bản</h2>
          {closeButton}
        </header>
        <div className="dpanel__body dpanel__body--pad">
          {gone ? (
            <EmptyState title="Không tìm thấy văn bản" description="Văn bản đã bị xóa hoặc bạn không có quyền xem." />
          ) : (
            <Alert kind="error" title="Không tải được văn bản" action={<Button onClick={reload}>Thử lại</Button>}>{error.message}</Alert>
          )}
        </div>
      </div>
    )
  }
  if (!data) {
    return (
      <div className={`dpanel dpanel--${variant}`}>
        <header className="dpanel__head dpanel__head--plain">
          <h2 className="dpanel__title">Chi tiết văn bản</h2>
          {closeButton}
        </header>
        <div className="dpanel__body dpanel__body--pad dpanel__loading">{loading && <Spinner label="Đang tải văn bản" size={24} />}</div>
      </div>
    )
  }

  const secret = data.level === 'mat'
  const hasTitle = Boolean((data.subject || data.title).trim())
  const identity = data.document_number || data.symbol ? documentSymbol(data) : ''
  const subline = [identity, data.document_type, data.issued_date ? formatDate(data.issued_date) : ''].filter(Boolean)
  const attention = data.state === 'needs_review' || data.state === 'needs_ocr' || data.state === 'failed'

  return (
    <div className={`dpanel dpanel--${variant}`}>
      <header className="dpanel__head">
        <FileTypeBadge name={data.original_name} size="lg" />
        <div className="dpanel__titles">
          <h2 className={hasTitle ? 'dpanel__title' : 'dpanel__title dpanel__title--empty'} title={documentTitle(data)}>
            {hasTitle ? data.subject || data.title : 'Chưa trích xuất được trích yếu'}
          </h2>
          <p className="dpanel__sub tnum">{subline.length > 0 ? subline.join(' · ') : data.original_name}</p>
          <div className="dpanel__chips">
            <StateChip state={data.state} size="lg" />
            <LevelChip level={data.level} size="lg" />
          </div>
        </div>
        <div className="dpanel__tools">
          {onOpenPage && <IconButton icon="expand" label="Mở trang riêng" size={20} onClick={onOpenPage} />}
          {closeButton}
        </div>
      </header>

      {secret && (
        <Callout tone="secret" title="Văn bản mật — chỉ chỉ huy xem được">
          {data.secret_reasons.length > 0 ? `Lý do: ${data.secret_reasons.join('; ')}.` : 'Người dùng thường không thấy văn bản này trong kho.'}
        </Callout>
      )}
      {attention && (
        <Callout tone={data.state === 'failed' ? 'danger' : 'warning'} title={data.state === 'failed' ? 'Không xử lý được văn bản' : data.state === 'needs_ocr' ? 'Cần OCR trước khi lập chỉ mục' : 'Cần rà soát thủ công'}>
          {data.state_detail || (data.state === 'failed' ? 'Thử xử lý lại hoặc kiểm tra tệp gốc.' : 'Bổ sung thông tin còn thiếu rồi lưu lại.')}
        </Callout>
      )}
      <DetailTabs items={tabs.map((key) => ({ key, label: TAB_LABELS[key], warnings: key === 'progress' ? data.warnings.length : 0 }))} value={tab} onChange={setTab} label="Chi tiết văn bản" idPrefix={`dp-${variant}`} />

      <div
        className={tab === 'preview' ? 'dpanel__body dpanel__body--preview' : 'dpanel__body dpanel__body--pad'}
        role="tabpanel"
        id={`dp-${variant}-panel`}
        aria-labelledby={`dp-${variant}-tab-${tab}`}
      >
        {tab === 'preview' &&
          (isInProgress(data) ? (
            <div className="dpanel__pending">
              <Spinner size={24} />
              <strong>Văn bản đang được xử lý</strong>
              <span>Bản xem trước sẽ có ngay khi hệ thống đọc xong nội dung.</span>
            </div>
          ) : (
            <div className="dpanel__paper"><DocumentView key={data.id} documentId={data.id} /></div>
          ))}

        {/* Kept mounted while another tab is shown so unsaved edits survive a look at the preview. */}
        <div hidden={tab !== 'info'}>
          <TagEditor key={`${data.id}:${data.updated_at}:${data.tags.join('|')}`} document={data} suggestions={tagSuggestions} onSaved={changed} />
          <MetadataForm key={`${data.id}:${data.updated_at}`} document={data} onSaved={changed}>
            <section className="dgroup" aria-label="Tệp">
              <h3 className="dgroup__title section-label">Tệp</h3>
              <div className="dgroup__grid">
                <ReadRow
                  label="Tệp gốc"
                  wide
                  value={
                    <span className="dfile">
                      <FileTypeBadge name={data.original_name} size="sm" />
                      <span className="dfile__name">{data.original_name}</span>
                      <span className="dfile__size tnum">{formatFileSize(data.file_size)}</span>
                    </span>
                  }
                />
                <ReadRow label="Người tải lên" value={data.uploaded_by_name || '—'} />
                <ReadRow label="Thời gian tải" value={<span className="tnum">{formatDateTime(data.uploaded_at)}</span>} />
                <ReadRow label="Đã lập chỉ mục" value={data.chunk_count > 0 ? `${formatNumber(data.chunk_count)} đoạn` : 'Chưa có đoạn nào'} />
              </div>
            </section>
          </MetadataForm>
        </div>

        {tab === 'progress' && (
          <div className="dpanel__stack">
            {data.warnings.length > 0 && (
              <Callout tone="warning" title={data.warnings.length > 1 ? `${data.warnings.length} cảnh báo khi xử lý` : 'Cảnh báo khi xử lý'}>
                <ul className="dcallout__list">{data.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
              </Callout>
            )}
            <ProcessingSteps steps={data.steps} uploadedAt={data.uploaded_at} uploadedBy={data.uploaded_by_name} />
          </div>
        )}
      </div>

      <footer className="dpanel__foot">
        <Button icon="download" onClick={() => download(data)} loading={downloading}>Tải tệp gốc</Button>
        {data.can_manage && (
          <>
            <Button icon="refresh" onClick={() => reprocess(data)} loading={reprocessing} disabled={isInProgress(data)}>Xử lý lại</Button>
            <span className="spacer" />
            <Button variant="danger" icon="trash" onClick={() => setConfirmDelete(true)}>Xóa</Button>
          </>
        )}
      </footer>

      {confirmDelete && (
        <ConfirmDialog
          title="Xóa văn bản"
          confirmLabel="Xóa văn bản"
          danger
          onCancel={() => setConfirmDelete(false)}
          onConfirm={() => remove(data)}
        >
          <p>Xóa văn bản <strong>{documentTitle(data)}</strong>? Tệp gốc và dữ liệu đã lập chỉ mục sẽ bị xóa vĩnh viễn, không khôi phục được.</p>
        </ConfirmDialog>
      )}
    </div>
  )
}
