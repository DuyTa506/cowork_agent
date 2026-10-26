import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import type { DocumentDetail } from '../api'
import { DocumentView } from '../components/DocumentView'
import type { ViewerHighlight } from '../components/DocumentViewer'
import { DocumentDetailPanel } from '../components/documents/DocumentDetailPanel'
import { EmptyState } from '../components/EmptyState'
import { Icon } from '../components/Icon'
import { useDocumentTitle } from '../hooks/useDocumentTitle'
import { documentTitle, isInProgress } from '../lib/documents'

/** /kho/:id: the paper on the left, the detail column on the right, a breadcrumb back to Kho. */
export function DocumentDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const documentId = Number(id)
  const [params] = useSearchParams()
  const highlight = parseHighlight(params.get('hl'))
  const [loaded, setLoaded] = useState<DocumentDetail | null>(null)
  useDocumentTitle(loaded ? documentTitle(loaded) : 'Chi tiết văn bản')

  if (!Number.isInteger(documentId) || documentId <= 0) {
    return <EmptyState title="Không tìm thấy văn bản" description={<Link to="/kho">Về Kho văn bản</Link>} />
  }

  return (
    <div className="dpage">
      <nav className="dpage__crumbs" aria-label="Đường dẫn">
        <Link className="dpage__back" to="/kho"><Icon name="arrowLeft" size={18} />Kho văn bản</Link>
        <Icon name="chevronRight" size={14} className="dpage__sep" />
        <span className="dpage__here" aria-current="page">{loaded ? documentTitle(loaded) : 'Chi tiết văn bản'}</span>
      </nav>
      <div className="dpage__body">
        <section className="dpage__paper" aria-label="Nội dung văn bản">
          {loaded && isInProgress(loaded) ? (
            <div className="dpanel__pending">
              <strong>Văn bản đang được xử lý</strong>
              <span>Bản xem trước sẽ có ngay khi hệ thống đọc xong nội dung.</span>
            </div>
          ) : (
            <DocumentView key={documentId} documentId={documentId} baseFontPx={15} highlight={highlight} />
          )}
        </section>
        <aside className="dpage__info" aria-label="Chi tiết văn bản">
          <DocumentDetailPanel
            key={documentId}
            documentId={documentId}
            variant="page"
            onLoaded={setLoaded}
            onDeleted={() => navigate('/kho', { replace: true })}
          />
        </aside>
      </div>
    </div>
  )
}

/** `?hl=3-5` marks paragraphs 3 to 5 (a cited passage); anything else means no highlight. */
function parseHighlight(value: string | null): ViewerHighlight | undefined {
  const match = value ? /^(\d+)(?:-(\d+))?$/.exec(value) : null
  if (!match) return undefined
  const from = Number(match[1])
  return { from, to: Number(match[2] ?? from) }
}
