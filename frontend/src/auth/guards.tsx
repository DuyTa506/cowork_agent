import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { Spinner } from '../components/Spinner'
import { useAuth } from './AuthContext'

/** Lets signed-in users through; everyone else goes to the login page and returns here afterwards. */
export function RequireAuth() {
  const { status } = useAuth()
  const location = useLocation()
  if (status === 'loading') return <div className="boot"><Spinner label="Đang kiểm tra phiên đăng nhập" size={28} /></div>
  if (status === 'anonymous') return <Navigate to="/dang-nhap" replace state={{ from: location.pathname + location.search }} />
  return <Outlet />
}

/** Restricts a route to administrators and commanders (unit-wide figures); other roles are sent to the document store. */
export function RequireViewer() {
  const { user } = useAuth()
  return user?.role === 'admin' || user?.role === 'commander' ? <Outlet /> : <Navigate to="/kho" replace />
}

/** Restricts a route to administrators; other roles are sent to the document store. */
export function RequireAdmin() {
  const { user } = useAuth()
  return user?.role === 'admin' ? <Outlet /> : <Navigate to="/kho" replace />
}
