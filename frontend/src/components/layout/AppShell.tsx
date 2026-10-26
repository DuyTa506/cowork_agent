import { useEffect, useRef, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { JobsProvider } from '../../hooks/useJobs'
import { useMediaQuery } from '../../hooks/useMediaQuery'
import { PageMetaProvider } from '../../hooks/usePageMeta'
import { useResizableWidth } from '../../hooks/useResizableWidth'
import { UnitsProvider } from '../../hooks/useUnits'
import { readStorage, writeStorage } from '../../lib/storage'
import { CommandPaletteProvider } from './CommandPalette'
import { RouteProgress } from './RouteProgress'
import { Sidebar } from './Sidebar'
import { Topbar } from './Topbar'

const SIDEBAR_KEY = 'qk3.sidebar'

/**
 * Frame of every signed-in page: navy sidebar (248 px, 72 px rail, phone drawer), 56 px top bar and the scrolling `<main>`.
 * It also provides the command palette, the job indicator and the breadcrumb context to everything inside.
 */
export function AppShell() {
  const { pathname } = useLocation()
  const narrow = useMediaQuery('(max-width: 1100px)')
  const phone = useMediaQuery('(max-width: 767.98px)')
  const tight = useMediaQuery('(max-width: 1699.98px)')
  const sidebarSize = useResizableWidth('qk3.sidebar.width', 248, 200, 360)
  const [preference, setPreference] = useState<'collapsed' | 'expanded' | 'hidden' | null>(() => {
    const stored = readStorage('local', SIDEBAR_KEY)
    return stored === 'collapsed' || stored === 'expanded' || stored === 'hidden' ? stored : null
  })
  const [drawerOpen, setDrawerOpen] = useState(false)
  const mainRef = useRef<HTMLElement>(null)

  // The rail is the default up to 1100 px wide; an explicit choice wins and is remembered.
  // The assistant needs room for chat + canvas: on screens below 1700 px it starts with the rail unless the user chose otherwise.
  const onAssistant = pathname.startsWith('/tro-ly')
  const hidden = !phone && preference === 'hidden'
  const collapsed = !phone && !hidden && (preference ? preference === 'collapsed' : narrow || (onAssistant && tight))
  const choose = (next: 'collapsed' | 'expanded' | 'hidden') => {
    setPreference(next)
    writeStorage('local', SIDEBAR_KEY, next)
  }
  const toggleCollapsed = () => {
    if (phone) return setDrawerOpen(false)
    choose(collapsed ? 'expanded' : 'collapsed')
  }
  const toggleHidden = () => (phone ? setDrawerOpen((open) => !open) : choose(hidden ? 'expanded' : 'hidden'))

  // Ctrl/⌘ + B hides or shows the whole sidebar, like the chat apps people know.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && !event.altKey && !event.shiftKey && event.key.toLowerCase() === 'b') {
        event.preventDefault()
        toggleHidden()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  useEffect(() => {
    setDrawerOpen(false)
    mainRef.current?.scrollTo({ top: 0 })
  }, [pathname])
  useEffect(() => {
    if (!phone) setDrawerOpen(false)
  }, [phone])

  return (
    <UnitsProvider>
      <JobsProvider>
        <PageMetaProvider>
          <CommandPaletteProvider>
            <div className="app" style={{ ['--sidebar-w' as string]: `${sidebarSize.width}px` }} data-sidebar={hidden ? 'hidden' : collapsed ? 'collapsed' : 'expanded'} data-drawer={drawerOpen ? 'open' : 'closed'}>
              <a className="skip-link" href="#main" onClick={(event) => { event.preventDefault(); mainRef.current?.focus() }}>Bỏ qua đến nội dung</a>
              <RouteProgress />
              <Sidebar size={sidebarSize} collapsed={collapsed} onHide={toggleHidden} onToggleCollapsed={toggleCollapsed} drawerOpen={drawerOpen} onCloseDrawer={() => setDrawerOpen(false)} />
              <div className="side-backdrop" onClick={() => setDrawerOpen(false)} aria-hidden="true" />
              <div className="app__col">
                <Topbar onOpenMenu={() => setDrawerOpen(true)} menuOpen={drawerOpen} sidebarHidden={hidden} onShowSidebar={toggleHidden} />
                <main className="main" id="main" ref={mainRef} tabIndex={-1}>
                  <Outlet />
                </main>
              </div>
            </div>
          </CommandPaletteProvider>
        </PageMetaProvider>
      </JobsProvider>
    </UnitsProvider>
  )
}
