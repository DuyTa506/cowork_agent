import { useState, type KeyboardEvent } from 'react'
import { AuditTab } from '../components/admin/AuditTab'
import { SettingsTab } from '../components/admin/SettingsTab'
import { UsersTab } from '../components/admin/UsersTab'
import { Icon, type IconName } from '../components/Icon'
import { PageHeader } from '../components/PageHeader'
import { tabPanelProps } from '../components/Tabs'
import { useDocumentTitle } from '../hooks/useDocumentTitle'

type AdminTab = 'users' | 'system' | 'audit'

const SECTIONS: { key: AdminTab; label: string; description: string; icon: IconName }[] = [
  { key: 'users', label: 'Tài khoản', description: 'Người dùng, vai trò và sơ đồ đơn vị', icon: 'users' },
  { key: 'system', label: 'Hệ thống', description: 'Mô hình AI, lưu trữ và chỉ mục', icon: 'server' },
  { key: 'audit', label: 'Nhật ký', description: 'Lịch sử thao tác của người dùng', icon: 'clipboard' },
]

/** "Quản trị hệ thống" (administrators only): accounts, model configuration and the audit trail, with a left sub-navigation. */
export function AdminPage() {
  useDocumentTitle('Quản trị hệ thống')
  const [tab, setTab] = useState<AdminTab>('users')
  const section = SECTIONS.find((item) => item.key === tab) ?? SECTIONS[0]!

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const index = SECTIONS.findIndex((item) => item.key === tab)
    const step = event.key === 'ArrowDown' || event.key === 'ArrowRight' ? 1 : event.key === 'ArrowUp' || event.key === 'ArrowLeft' ? -1 : 0
    if (step === 0) return
    event.preventDefault()
    const next = SECTIONS[(index + step + SECTIONS.length) % SECTIONS.length]
    if (!next) return
    setTab(next.key)
    document.getElementById(`admin-tab-${next.key}`)?.focus()
  }

  return (
    <>
      <PageHeader title="Quản trị hệ thống" />
      <div className="admin">
        <div className="admin__nav" role="tablist" aria-label="Mục quản trị" aria-orientation="vertical" onKeyDown={onKeyDown}>
          <span className="section-label admin__nav-label" aria-hidden="true">Quản trị</span>
          {SECTIONS.map((item) => (
            <button
              key={item.key}
              type="button"
              role="tab"
              id={`admin-tab-${item.key}`}
              aria-selected={item.key === tab}
              aria-controls={`admin-panel-${item.key}`}
              tabIndex={item.key === tab ? 0 : -1}
              className={item.key === tab ? 'admin__tab admin__tab--on' : 'admin__tab'}
              onClick={() => setTab(item.key)}
            >
              <Icon name={item.icon} size={20} weight="regular" />
              <span>{item.label}</span>
            </button>
          ))}
        </div>
        <div {...tabPanelProps('admin', tab)} className="admin__panel">
          <header className="admin__head">
            <h2>{section.label}</h2>
            <p>{section.description}</p>
          </header>
          {tab === 'users' && <UsersTab />}
          {tab === 'system' && <SettingsTab />}
          {tab === 'audit' && <AuditTab />}
        </div>
      </div>
    </>
  )
}
