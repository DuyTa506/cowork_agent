import { Suspense, lazy } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import { RequireAdmin, RequireAuth, RequireViewer } from './auth/guards'
import { AppShell } from './components/layout/AppShell'
import { Spinner } from './components/Spinner'
import { ToastProvider } from './components/Toast'

// Every page is its own chunk: the sign-in page does not download the editor, the viewer or the admin screens.
const LoginPage = lazy(() => import('./pages/LoginPage').then((module) => ({ default: module.LoginPage })))
const AssistantPage = lazy(() => import('./pages/AssistantPage').then((module) => ({ default: module.AssistantPage })))
const DocumentsPage = lazy(() => import('./pages/DocumentsPage').then((module) => ({ default: module.DocumentsPage })))
const DocumentDetailPage = lazy(() => import('./pages/DocumentDetailPage').then((module) => ({ default: module.DocumentDetailPage })))
const CheckPage = lazy(() => import('./pages/CheckPage').then((module) => ({ default: module.CheckPage })))
const SpellPage = lazy(() => import('./pages/SpellPage').then((module) => ({ default: module.SpellPage })))
const DashboardPage = lazy(() => import('./pages/DashboardPage').then((module) => ({ default: module.DashboardPage })))
const AdminPage = lazy(() => import('./pages/AdminPage').then((module) => ({ default: module.AdminPage })))
// Dev-only living style guide (not in the production bundle).
const StyleGuidePage = import.meta.env.DEV ? lazy(() => import('./pages/StyleGuidePage').then((module) => ({ default: module.StyleGuidePage }))) : null
const NotFoundPage = lazy(() => import('./pages/NotFoundPage').then((module) => ({ default: module.NotFoundPage })))

/** Providers and the route table. */
export function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <AuthProvider>
          <Suspense fallback={<div className="boot"><Spinner label="Đang tải" size={28} /></div>}>
            <Routes>
              <Route path="/dang-nhap" element={<LoginPage />} />
              {StyleGuidePage && <Route path="/_ui" element={<StyleGuidePage />} />}
              <Route element={<RequireAuth />}>
                <Route element={<AppShell />}>
                  <Route path="/" element={<Navigate to="/kho" replace />} />
                  <Route path="/tro-ly" element={<AssistantPage />} />
                  <Route path="/kho" element={<DocumentsPage />} />
                  <Route path="/kho/:id" element={<DocumentDetailPage />} />
                  <Route path="/kiem-tra" element={<CheckPage />} />
                  <Route path="/chinh-ta" element={<SpellPage />} />
                  <Route element={<RequireViewer />}>
                    <Route path="/thong-ke" element={<DashboardPage />} />
                  </Route>
                  <Route element={<RequireAdmin />}>
                    <Route path="/quan-tri" element={<AdminPage />} />
                  </Route>
                  <Route path="*" element={<NotFoundPage />} />
                </Route>
              </Route>
            </Routes>
          </Suspense>
        </AuthProvider>
      </ToastProvider>
    </BrowserRouter>
  )
}
