import type { KeyboardEvent, ReactNode } from 'react'
import type { ResizableWidth } from '../../hooks/useResizableWidth'
import { Icon } from '../Icon'
import { ResizeHandle } from '../ResizeHandle'

export interface PanelTab {
  key: string
  label: string
  /** Small visual before the label: an icon or a file-type badge. */
  lead: ReactNode
  closable: boolean
  content: ReactNode
}

interface SidePanelProps {
  tabs: PanelTab[]
  active: string
  onSelect: (key: string) => void
  onClose: (key: string) => void
  /** Narrow screens show the panel over the chat; this returns to the chat. */
  onBack: () => void
  /** Draggable width (wide screens); without it the panel keeps its stylesheet width. */
  size?: ResizableWidth
}

const panelId = (key: string) => `dock-${key.replace(/[^a-z0-9]/gi, '-')}`

/**
 * Right-hand area next to the chat: one tab for the Canvas draft and one for each opened source. Every tab keeps its content
 * mounted (hidden when inactive) so scroll position, edits in progress and check results survive.
 */
export function SidePanel({ tabs, active, onSelect, onClose, onBack, size }: SidePanelProps) {
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0
    if (step === 0) return
    event.preventDefault()
    const index = tabs.findIndex((tab) => tab.key === active)
    const next = tabs[(index + step + tabs.length) % tabs.length]
    if (!next) return
    onSelect(next.key)
    document.getElementById(`${panelId(next.key)}-tab`)?.focus()
  }
  return (
    <aside className={tabs.length === 1 && !tabs[0]?.closable ? 'dock dock--single' : 'dock'} aria-label="Canvas và văn bản nguồn" style={size ? { flexBasis: size.width } : undefined}>
      {size && <ResizeHandle size={size} edge="left" label="Độ rộng khung Canvas và nguồn" />}
      <div className="dock__tabs">
        <button type="button" className="dock__back" onClick={onBack}>
          <Icon name="arrowLeft" size={16} />
          Trò chuyện
        </button>
        <div className="dock__list" role="tablist" aria-label="Các thẻ bên phải" onKeyDown={onKeyDown}>
          {tabs.map((tab) => {
            const selected = tab.key === active
            return (
              <div key={tab.key} className={selected ? 'dtab dtab--on' : 'dtab'}>
                <button
                  type="button"
                  role="tab"
                  id={`${panelId(tab.key)}-tab`}
                  aria-selected={selected}
                  aria-controls={panelId(tab.key)}
                  tabIndex={selected ? 0 : -1}
                  className="dtab__label"
                  onClick={() => onSelect(tab.key)}
                  title={tab.label}
                >
                  <span className="dtab__lead">{tab.lead}</span>
                  <span className="dtab__text">{tab.label}</span>
                </button>
                {tab.closable && (
                  <button type="button" className="dtab__close" aria-label={`Đóng thẻ ${tab.label}`} title="Đóng thẻ" onClick={() => onClose(tab.key)}>
                    <Icon name="close" size={14} />
                  </button>
                )}
              </div>
            )
          })}
        </div>
      </div>
      {tabs.map((tab) => (
        <div key={tab.key} role="tabpanel" id={panelId(tab.key)} aria-labelledby={`${panelId(tab.key)}-tab`} className="dock__body" hidden={tab.key !== active}>
          {tab.content}
        </div>
      ))}
    </aside>
  )
}
