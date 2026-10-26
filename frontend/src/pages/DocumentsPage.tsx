import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { documentsApi, type DocumentSummary } from '../api'
import { useAuth } from '../auth/AuthContext'
import { Alert } from '../components/Alert'
import { Button } from '../components/Button'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { ActiveFilters } from '../components/documents/ActiveFilters'
import { BrowsePanel } from '../components/documents/BrowsePanel'
import { DocumentDrawer } from '../components/documents/DocumentDrawer'
import { DocumentFilterBar } from '../components/documents/DocumentFilterBar'
import { DocumentTable, type RowActions } from '../components/documents/DocumentTable'
import { StatStrip } from '../components/documents/StatStrip'
import { UploadDialog } from '../components/documents/UploadDialog'
import { FileTypeBadge } from '../components/FileTypeBadge'
import { Icon } from '../components/Icon'
import { Pagination } from '../components/Pagination'
import { ResizeHandle } from '../components/ResizeHandle'
import { useToast } from '../components/Toast'
import { useAsyncData } from '../hooks/useAsyncData'
import { useDocumentTitle } from '../hooks/useDocumentTitle'
import { useMediaQuery } from '../hooks/useMediaQuery'
import { useResizableWidth } from '../hooks/useResizableWidth'
import { useUnits } from '../hooks/useUnits'
import { EMPTY_FILTERS, hasFilters, isYearTag, readView, writeView, yearOf, type DocumentFilters, type ListView } from '../lib/documentFilters'
import { STATE_TABS, canManage, documentTitle, downloadOriginal, isInProgress, tabCount, type StateTabKey } from '../lib/documents'
import { formatNumber } from '../lib/format'
import { readStorage, writeStorage } from '../lib/storage'

const PAGE_SIZE = 25
const POLL_MS = 3000
const PANEL_KEY = 'qk3.kho.panel.hidden'

/** Whether the browse panel starts hidden: what the user chose last time, else hidden on screens too narrow to share with a table. */
function initialPanelHidden(): boolean {
  const stored = readStorage('local', PANEL_KEY)
  return stored === null ? window.innerWidth < 1280 : stored === '1'
}

/**
 * "Kho văn bản": a browse panel (folded unit tree, type / year / tag chips with counts) beside a paged list of the documents the
 * user may read, with a detail drawer and upload. Every filter, the state card and the page live in the address.
 */
export function DocumentsPage() {
  useDocumentTitle('Kho văn bản')
  const navigate = useNavigate()
  const location = useLocation()
  const notify = useToast()
  const { user } = useAuth()
  const { units, byId } = useUnits()
  const [params, setParams] = useSearchParams()
  const view = useMemo(() => readView(params), [params])
  const { filters, tab, page } = view
  const offset = page * PAGE_SIZE
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [upload, setUpload] = useState<null | { pick: boolean }>(null)
  const [panelHidden, setPanelHidden] = useState(initialPanelHidden)
  const [deleting, setDeleting] = useState<DocumentSummary | null>(null)
  const panelSize = useResizableWidth('qk3.kho.panel', 272, 224, 440)
  const stacked = useMediaQuery('(max-width: 900px)')

  const showPanel = (visible: boolean) => {
    setPanelHidden(!visible)
    writeStorage('local', PANEL_KEY, visible ? '0' : '1')
  }

  const go = useCallback((next: ListView) => setParams(writeView(next), { replace: true }), [setParams])
  const changeFilters = useCallback((patch: Partial<DocumentFilters>) => go({ filters: { ...filters, ...patch }, tab, page: 0 }), [go, filters, tab])
  const setTab = (key: StateTabKey) => go({ filters, tab: key, page: 0 })
  const setPage = (next: number) => go({ filters, tab, page: next })
  const clearFilters = () => go({ filters: EMPTY_FILTERS, tab: 'all', page: 0 })
  const pickTag = useCallback((tag: string) => changeFilters({ tags: filters.tags.includes(tag) ? filters.tags : [...filters.tags, tag] }), [changeFilters, filters.tags])

  // The command palette's "Tải văn bản lên" arrives as router state { action: 'upload' }.
  useEffect(() => {
    if ((location.state as { action?: string } | null)?.action !== 'upload') return
    setUpload({ pick: false })
    navigate(location.pathname + location.search, { replace: true, state: null })
  }, [location.state, location.pathname, location.search, navigate])

  const states = STATE_TABS.find((candidate) => candidate.key === tab)?.states ?? []
  const { data, error, loading, reload } = useAsyncData(
    (signal) =>
      documentsApi.listDocuments(
        {
          q: filters.q,
          states,
          documentType: filters.types.join(','),
          unitId: filters.unitId,
          level: filters.level,
          tags: filters.tags,
          dateFrom: filters.dateFrom,
          dateTo: filters.dateTo,
          limit: PAGE_SIZE,
          offset,
        },
        signal,
      ),
    [tab, filters.q, filters.types.join('|'), filters.unitId, filters.level, filters.tags.join('|'), filters.dateFrom, filters.dateTo, offset],
    { pollMs: POLL_MS, shouldPoll: (list) => list.items.some(isInProgress) },
  )
  const facetsState = useAsyncData((signal) => documentsApi.getFacets(signal), [])
  const { data: facets, reload: reloadFacets } = facetsState
  const reloadAll = useCallback(() => { reload(); reloadFacets() }, [reload, reloadFacets])
  const tagSuggestions = useMemo(() => (facets?.tags ?? []).map((tag) => tag.value).filter((tag) => !isYearTag(tag)), [facets])

  // After deleting the last row of the last page, or following an old link to a page that no longer exists, step back to one that does.
  useEffect(() => {
    if (data && data.items.length === 0 && data.total > 0 && page > 0) setPage(Math.ceil(data.total / PAGE_SIZE) - 1)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, page])

  const actions = useMemo<RowActions>(
    () => ({
      onOpen: (document) => setSelectedId(document.id),
      onOpenPage: (document) => navigate(`/kho/${document.id}`),
      onDownload: (document) => {
        downloadOriginal(document).catch((failure: unknown) => notify(failure instanceof Error ? failure.message : 'Không tải được tệp gốc.', 'error'))
      },
      onReprocess: (document) => {
        documentsApi
          .reprocessDocument(document.id)
          .then(() => { notify('Đã đưa văn bản vào hàng đợi xử lý lại.'); reload() })
          .catch((failure: unknown) => notify(failure instanceof Error ? failure.message : 'Không xử lý lại được.', 'error'))
      },
      onDelete: (document) => setDeleting(document),
      canManage: (document) => canManage(document, user),
      onPickTag: pickTag,
    }),
    [navigate, notify, reload, user, pickTag],
  )

  const rows = data ? data.items : null
  const total = data ? tabCount(STATE_TABS[0] ?? { key: 'all', label: '', states: [], tone: 'ink', icon: 'folder' }, data.states) : 0
  const stateFiltered = tab !== 'all'
  const filtering = hasFilters(filters) || stateFiltered
  const panelFilters = (filters.unitId ? 1 : 0) + filters.types.length + (yearOf(filters) ? 1 : 0) + filters.tags.length
  const stateLabel = STATE_TABS.find((candidate) => candidate.key === tab)?.label ?? ''
  const pageCount = rows?.length ?? 0

  const confirmDelete = async (document: DocumentSummary) => {
    await documentsApi.deleteDocument(document.id)
    notify('Đã xóa văn bản.')
    setDeleting(null)
    if (selectedId === document.id) setSelectedId(null)
    reloadAll()
  }

  return (
    <div className="docs">
      <header className="dhead">
        <div className="dhead__text">
          <h1 className="dhead__title">Kho văn bản</h1>
          <p className="dhead__desc">Văn bản tải lên được trích xuất trường, chia đoạn và lập chỉ mục để tra cứu, xem và hỏi đáp.</p>
        </div>
        <div className="dhead__actions">
          <Button icon="folder" onClick={() => setUpload({ pick: true })}>Tải nhiều tệp</Button>
          <Button variant="primary" icon="upload" onClick={() => setUpload({ pick: false })}>Tải văn bản lên</Button>
        </div>
      </header>

      <StatStrip counts={data?.states ?? null} value={tab} onChange={setTab} />

      <div className={['dlayout', stacked && 'dlayout--stacked', !panelHidden && !stacked && 'dlayout--paneled'].filter(Boolean).join(' ')}>
        {!panelHidden && (
          <div className="dlayout__panel" style={stacked ? undefined : { flexBasis: panelSize.width, width: panelSize.width }}>
            <BrowsePanel facets={facets} units={units} filters={filters} onChange={changeFilters} onHide={() => showPanel(false)} />
            {!stacked && <ResizeHandle size={panelSize} edge="right" label="Độ rộng bảng duyệt kho" />}
          </div>
        )}

        <div className="dlayout__main">
          <DocumentFilterBar filters={filters} onChange={changeFilters} onShowPanel={panelHidden ? () => showPanel(true) : undefined} panelFilters={panelFilters} />
          <ActiveFilters
            filters={filters}
            unitName={(id) => byId.get(id)?.name ?? id}
            stateLabel={stateFiltered ? stateLabel : ''}
            onChange={changeFilters}
            onClearState={() => setTab('all')}
            onClearAll={clearFilters}
          />

          <section className="dcard" aria-label="Danh sách văn bản">
            <div className="dcard__body">
            {error && !data && (
              <div className="dcard__pad"><Alert kind="error" title="Không tải được danh sách" action={<Button onClick={reload}>Thử lại</Button>}>{error.message}</Alert></div>
            )}
            {!(error && !data) && (loading && !data ? <DocumentTable documents={null} selectedId={null} onSelect={() => undefined} actions={actions} /> : null)}
            {data && rows && rows.length > 0 && <DocumentTable documents={rows} selectedId={selectedId} activeTags={filters.tags} onSelect={(document) => setSelectedId(document.id)} actions={actions} />}
            {data && rows && rows.length === 0 && (
              filtering ? (
                <div className="dempty">
                  <span className="dempty__icon"><Icon name="search" size={24} /></span>
                  <h2 className="dempty__title">Không có văn bản phù hợp</h2>
                  <p className="dempty__text">Thử đổi từ khóa hoặc bỏ bớt điều kiện lọc để xem thêm văn bản.</p>
                  <Button icon="close" onClick={clearFilters}>Xóa lọc</Button>
                </div>
              ) : (
                <div className="dempty">
                  <span className="dempty__badges" aria-hidden="true">
                    <FileTypeBadge name="x.docx" size="lg" />
                    <FileTypeBadge name="x.doc" size="lg" />
                    <FileTypeBadge name="x.pdf" size="lg" />
                  </span>
                  <h2 className="dempty__title">Kho văn bản còn trống</h2>
                  <p className="dempty__text">Tải văn bản lên để hệ thống trích xuất, lập chỉ mục và cho phép tra cứu, hỏi đáp.</p>
                  <Button variant="primary" icon="upload" onClick={() => setUpload({ pick: false })}>Tải văn bản lên</Button>
                </div>
              )
            )}
            </div>
            {data && data.total > 0 && (
              <div className="dcard__foot">
                <Pagination offset={offset} limit={PAGE_SIZE} total={data.total} noun="văn bản" onOffsetChange={(next) => setPage(Math.floor(next / PAGE_SIZE))} />
              </div>
            )}
          </section>
        </div>
      </div>
      <p className="sr-only" role="status">{data ? `Hiển thị ${formatNumber(pageCount)} văn bản` : 'Đang tải danh sách'}</p>
      <p className="dfoot"><Icon name="shield" size={16} /><span>Người dùng chỉ thấy văn bản thuộc đơn vị và mức độ mình được phép xem.{data && total > 0 && <> Kho có <strong className="tnum">{formatNumber(total)}</strong> văn bản.</>}</span></p>

      {selectedId !== null && (
        <DocumentDrawer
          key={selectedId}
          documentId={selectedId}
          onClose={() => setSelectedId(null)}
          onOpenPage={() => navigate(`/kho/${selectedId}`)}
          onChanged={reloadAll}
          onDeleted={() => { setSelectedId(null); reloadAll() }}
          tagSuggestions={tagSuggestions}
        />
      )}

      {deleting && (
        <ConfirmDialog title="Xóa văn bản" confirmLabel="Xóa văn bản" danger onCancel={() => setDeleting(null)} onConfirm={() => confirmDelete(deleting)}>
          <p>Xóa văn bản <strong>{documentTitle(deleting)}</strong>? Tệp gốc và dữ liệu đã lập chỉ mục sẽ bị xóa vĩnh viễn, không khôi phục được.</p>
        </ConfirmDialog>
      )}

      {upload && <UploadDialog pickOnOpen={upload.pick} onClose={() => setUpload(null)} onUploaded={reloadAll} />}
    </div>
  )
}
