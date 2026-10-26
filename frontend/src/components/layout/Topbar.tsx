import { Fragment } from 'react'
import { Link } from 'react-router-dom'
import { useCrumbs } from '../../hooks/usePageMeta'
import { useJobs } from '../../hooks/useJobs'
import { formatNumber } from '../../lib/format'
import { Icon } from '../Icon'
import { IconButton } from '../IconButton'
import { Spinner } from '../Spinner'
import { useCommandPalette } from './CommandPalette'
import { ThemeToggle } from './ThemeToggle'
import { UserMenu } from './UserMenu'

/** True on Apple platforms, where the palette shortcut is shown as ⌘K. */
const MAC = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)

/** 56 px bar above the content: menu button (phones), breadcrumb, search / command palette, job indicator, theme, account. */
export function Topbar({ onOpenMenu, menuOpen, sidebarHidden, onShowSidebar }: { onOpenMenu: () => void; menuOpen: boolean; sidebarHidden: boolean; onShowSidebar: () => void }) {
  const crumbs = useCrumbs()
  const { active } = useJobs()
  const palette = useCommandPalette()

  return (
    <header className="topbar">
      <IconButton icon="menu" label="Mở menu" className="topbar__menu" onClick={onOpenMenu} aria-expanded={menuOpen} aria-controls="sidebar" />
      {sidebarHidden && <IconButton icon="panelLeftOpen" label="Hiện thanh bên (Ctrl+B)" className="topbar__show" onClick={onShowSidebar} aria-controls="sidebar" />}
      <nav className="crumbs" aria-label="Vị trí hiện tại">
        <ol>
          {crumbs.map((crumb, index) => {
            const last = index === crumbs.length - 1
            return (
              <Fragment key={`${crumb.label}-${index}`}>
                <li>
                  {crumb.to && !last ? <Link to={crumb.to}>{crumb.label}</Link> : <span aria-current={last ? 'page' : undefined}>{crumb.label}</span>}
                  {!last && <Icon name="chevronRight" size={14} />}
                </li>
              </Fragment>
            )
          })}
        </ol>
      </nav>
      <button type="button" className="topbar__search" onClick={palette.open} aria-label="Tìm kiếm và lệnh nhanh" aria-keyshortcuts="Control+K">
        <Icon name="search" size={18} />
        <span>Tìm văn bản, lệnh…</span>
        <span className="kbd-group" aria-hidden="true"><kbd>{MAC ? '⌘' : 'Ctrl'}</kbd><kbd>K</kbd></span>
      </button>
      <div className="topbar__actions">
        {active > 0 && (
          <Link to="/kho" className="jobs" title={`${active} văn bản đang chờ hoặc đang được xử lý`}>
            <Spinner size={14} />
            <span className="jobs__count">{formatNumber(active)}</span>
            <span className="jobs__label">đang xử lý</span>
            <span className="sr-only"> văn bản đang chờ hoặc đang được xử lý</span>
          </Link>
        )}
        <ThemeToggle />
        <UserMenu variant="avatar" />
      </div>
    </header>
  )
}
