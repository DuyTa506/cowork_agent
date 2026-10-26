import type { KeyboardEvent, ReactNode } from 'react'
import { Icon, type IconName } from './Icon'

export interface TabItem<K extends string> {
  key: K
  label: string
  /** Count pill after the label. */
  count?: ReactNode
  icon?: IconName
}

interface TabsProps<K extends string> {
  items: TabItem<K>[]
  value: K
  onChange: (key: K) => void
  /** Names the tab list for assistive technology. */
  label: string
  /** Prefix for element ids; the panel must use `tabPanelProps(idPrefix, key)`. */
  idPrefix: string
  className?: string
}

/** Props for the element that shows the content of tab `key`. */
export function tabPanelProps(idPrefix: string, key: string) {
  return { role: 'tabpanel', id: `${idPrefix}-panel-${key}`, 'aria-labelledby': `${idPrefix}-tab-${key}`, tabIndex: 0 } as const
}

/** Underlined tab strip (WAI-ARIA tabs: Left/Right move between tabs, Home/End jump to the ends). */
export function Tabs<K extends string>({ items, value, onChange, label, idPrefix, className }: TabsProps<K>) {
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const index = items.findIndex((item) => item.key === value)
    let next: TabItem<K> | undefined
    if (event.key === 'ArrowRight') next = items[(index + 1) % items.length]
    else if (event.key === 'ArrowLeft') next = items[(index - 1 + items.length) % items.length]
    else if (event.key === 'Home') next = items[0]
    else if (event.key === 'End') next = items[items.length - 1]
    else return
    event.preventDefault()
    if (!next) return
    onChange(next.key)
    document.getElementById(`${idPrefix}-tab-${next.key}`)?.focus()
  }
  return (
    <div className={['tabs', className].filter(Boolean).join(' ')} role="tablist" aria-label={label} onKeyDown={onKeyDown}>
      {items.map((item) => {
        const selected = item.key === value
        return (
          <button
            key={item.key}
            type="button"
            role="tab"
            id={`${idPrefix}-tab-${item.key}`}
            aria-selected={selected}
            aria-controls={`${idPrefix}-panel-${item.key}`}
            tabIndex={selected ? 0 : -1}
            className={selected ? 'tab tab--on' : 'tab'}
            onClick={() => onChange(item.key)}
          >
            {item.icon && <Icon name={item.icon} size={16} />}
            {item.label}
            {item.count !== undefined && <span className="tab__count">{item.count}</span>}
          </button>
        )
      })}
    </div>
  )
}
