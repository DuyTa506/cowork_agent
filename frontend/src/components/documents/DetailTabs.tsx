import type { KeyboardEvent } from 'react'

export interface DetailTabItem<K extends string> {
  key: K
  label: string
  /** A small warning count after the label. */
  warnings?: number
}

interface DetailTabsProps<K extends string> {
  items: DetailTabItem<K>[]
  value: K
  onChange: (key: K) => void
  label: string
  idPrefix: string
}

/** Tab strip of the detail panel: brass underline on the active tab (WAI-ARIA tabs; arrow keys move between tabs). */
export function DetailTabs<K extends string>({ items, value, onChange, label, idPrefix }: DetailTabsProps<K>) {
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const index = items.findIndex((item) => item.key === value)
    const step = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0
    const edge = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : null
    if (step === 0 && edge === null) return
    event.preventDefault()
    const next = edge !== null ? items[edge] : items[(index + step + items.length) % items.length]
    if (!next) return
    onChange(next.key)
    document.getElementById(`${idPrefix}-tab-${next.key}`)?.focus()
  }
  return (
    <div className="dtabs" role="tablist" aria-label={label} onKeyDown={onKeyDown}>
      {items.map((item) => {
        const selected = item.key === value
        return (
          <button
            key={item.key}
            type="button"
            role="tab"
            id={`${idPrefix}-tab-${item.key}`}
            aria-selected={selected}
            aria-controls={`${idPrefix}-panel`}
            tabIndex={selected ? 0 : -1}
            className={selected ? 'dtab dtab--on' : 'dtab'}
            onClick={() => onChange(item.key)}
          >
            {item.label}
            {item.warnings ? <span className="dtab__badge" title={`${item.warnings} cảnh báo`}><span className="sr-only">{item.warnings} cảnh báo</span><span aria-hidden="true">{item.warnings}</span></span> : null}
          </button>
        )
      })}
    </div>
  )
}
