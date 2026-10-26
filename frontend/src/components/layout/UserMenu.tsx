import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../auth/AuthContext'
import { ROLE_LABELS } from '../../lib/labels'
import { Avatar } from '../Avatar'
import { Icon } from '../Icon'
import { Menu, type MenuEntry } from '../Menu'
import { ChangePasswordDialog } from './ChangePasswordDialog'

/**
 * Account menu (name, unit, change password, sign out). `card` is the sidebar footer card, `avatar` the top-bar button;
 * both open the same menu.
 */
export function UserMenu({ variant }: { variant: 'card' | 'avatar' }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [changing, setChanging] = useState(false)
  if (!user) return null
  const name = user.full_name || user.username
  const unit = user.unit_name || user.unit_id

  const items: MenuEntry[] = [
    { type: 'header', key: 'who', title: name, subtitle: `${ROLE_LABELS[user.role]} · ${unit}` },
    { key: 'password', label: 'Đổi mật khẩu', icon: 'key', onSelect: () => setChanging(true) },
    { type: 'separator', key: 'sep' },
    { key: 'logout', label: 'Đăng xuất', icon: 'logout', danger: true, onSelect: () => { logout(); navigate('/dang-nhap', { replace: true }) } },
  ]

  return (
    <>
      <Menu
        label="Tài khoản"
        items={items}
        placement={variant === 'card' ? 'top-start' : 'bottom-end'}
        trigger={(props, { open }) =>
          variant === 'card' ? (
            <button {...props} type="button" className="user-card" aria-label={`Tài khoản: ${name}`} aria-expanded={open}>
              <Avatar name={name} onDark className="user-card__avatar" />
              <span className="user-card__text">
                <span className="user-card__name">{name}</span>
                <span className="user-card__unit">{unit}</span>
              </span>
              <Icon name="chevronsUpDown" size={16} />
            </button>
          ) : (
            <button {...props} type="button" className="topbar-avatar" aria-label={`Tài khoản: ${name}`} aria-expanded={open}>
              <Avatar name={name} />
            </button>
          )
        }
      />
      {changing && <ChangePasswordDialog onClose={() => setChanging(false)} />}
    </>
  )
}
