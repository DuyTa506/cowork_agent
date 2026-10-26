import { Link } from 'react-router-dom'
import { EmptyState } from '../components/EmptyState'
import { PageHeader } from '../components/PageHeader'
import { useDocumentTitle } from '../hooks/useDocumentTitle'

/** Shown for addresses that match no route. */
export function NotFoundPage() {
  useDocumentTitle('Không tìm thấy trang')
  return (
    <>
      <PageHeader title="Không tìm thấy trang" />
      <EmptyState icon="fileX" title="Không tìm thấy trang" description="Địa chỉ này không tồn tại hoặc đã được chuyển." action={<Link className="btn btn--primary" to="/kho">Về Kho văn bản</Link>} />
    </>
  )
}
