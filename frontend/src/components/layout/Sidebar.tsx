import { useRef } from 'react'
import { NavLink } from 'react-router-dom'
import { useAuth } from '../../auth/AuthContext'
import { useJobs } from '../../hooks/useJobs'
import { useLayer } from '../../hooks/useLayer'
import type { ResizableWidth } from '../../hooks/useResizableWidth'
import { Icon } from '../Icon'
import { IconButton } from '../IconButton'
import { ResizeHandle } from '../ResizeHandle'
import { Tooltip } from '../Tooltip'
import { NAV, canSee } from './nav'
import { UserMenu } from './UserMenu'

interface SidebarProps {
  /** Draggable expanded width. */
  size: ResizableWidth
  /** Hides the whole sidebar (the top bar then offers a button to bring it back). */
  onHide: () => void
  /** 72 px rail (icons only). */
  collapsed: boolean
  onToggleCollapsed: () => void
  /** Phone drawer state; the sidebar is off-canvas below 768 px unless open. */
  drawerOpen: boolean
  onCloseDrawer: () => void
}

/** Navy navigation column: emblem, nav items with a gold marker on the active one, system status and the user card. */
export function Sidebar({ size, onHide, collapsed, onToggleCollapsed, drawerOpen, onCloseDrawer }: SidebarProps) {
  const { user } = useAuth()
  const { reachable, active } = useJobs()
  const ref = useRef<HTMLElement>(null)
  useLayer(ref, { onClose: onCloseDrawer, enabled: drawerOpen })

  return (
    <aside ref={ref} className="side" id="sidebar" aria-label="Thanh điều hướng" tabIndex={-1}>
      {!collapsed && <ResizeHandle size={size} edge="right" label="Độ rộng thanh điều hướng" />}
      <div className="brand">
        <img className="brand__logo" src="/logo-128.png" width={40} height={40} alt="" />
        <span className="brand__text">
          <span className="brand__title">QUÂN KHU 3</span>
          <span className="brand__sub">Hỗ trợ xử lý văn bản</span>
        </span>
        <IconButton icon="close" label="Đóng menu" className="side__close" onClick={onCloseDrawer} />
        <IconButton icon="panelLeftClose" label="Ẩn thanh bên (Ctrl+B)" className="side__hide" onClick={onHide} />
      </div>
      <nav aria-label="Chức năng chính" className="side__nav">
        {NAV.filter((entry) => canSee(entry, user?.role)).map((entry) => {
          const link = (
            <NavLink key={entry.to} to={entry.to} className={({ isActive }) => (isActive ? 'nav-item nav-item--on' : 'nav-item')} aria-label={collapsed ? entry.label : undefined} onClick={onCloseDrawer}>
              <Icon name={entry.icon} size={20} />
              <span className="nav-item__label">{entry.label}</span>
            </NavLink>
          )
          return collapsed ? <Tooltip key={entry.to} content={entry.label} side="right" delay={150}>{link}</Tooltip> : link
        })}
      </nav>
      <div className="side__foot">
        <div className={['side-status', !reachable && 'side-status--down'].filter(Boolean).join(' ')} role="status" title={reachable ? 'Mạng nội bộ · phiên được kiểm soát' : undefined}>
          <span className="side-status__dot" aria-hidden="true" />
          <span className="side-status__text">
            <strong>{reachable ? 'Hệ thống hoạt động' : 'Mất kết nối máy chủ'}</strong>
            <span>{reachable ? (active > 0 ? `Đang xử lý ${active} văn bản` : 'Mạng nội bộ') : 'Đang thử kết nối lại…'}</span>
          </span>
        </div>
        <UserMenu variant="card" />
        <button type="button" className="side-toggle" onClick={onToggleCollapsed} aria-label={collapsed ? 'Mở rộng thanh bên' : 'Thu gọn thanh bên'} aria-pressed={collapsed}>
          <Icon name={collapsed ? 'panelLeftOpen' : 'panelLeftClose'} size={20} />
          <span className="side-toggle__label">Thu gọn</span>
        </button>
      </div>
    </aside>
  )
}
