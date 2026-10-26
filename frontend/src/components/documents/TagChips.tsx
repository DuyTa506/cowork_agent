import type { MouseEvent } from 'react'

interface TagChipsProps {
  tags: string[]
  /** Tags currently used as a filter are drawn as pressed. */
  active?: readonly string[]
  /** How many to show before "+n". */
  max?: number
  /** Makes the chips buttons that filter by the tag; without it they are plain labels. */
  onPick?: (tag: string) => void
}

/** A row of small tag chips: the first few, then "+n". In the list a click on one filters by it (and does not open the row). */
export function TagChips({ tags, active = [], max = 3, onPick }: TagChipsProps) {
  if (tags.length === 0) return null
  const shown = tags.slice(0, max)
  const rest = tags.slice(max)
  const stop = (event: MouseEvent) => event.stopPropagation()
  return (
    <ul className="tagrow" aria-label="Thẻ" onClick={stop}>
      {shown.map((tag) => (
        <li key={tag}>
          {onPick ? (
            <button type="button" className={active.includes(tag) ? 'tagchip is-on' : 'tagchip'} aria-pressed={active.includes(tag)} title={`Lọc theo thẻ “${tag}”`} onClick={() => onPick(tag)}>{tag}</button>
          ) : (
            <span className="tagchip">{tag}</span>
          )}
        </li>
      ))}
      {rest.length > 0 && <li><span className="tagchip tagchip--more" title={rest.join(', ')}>+{rest.length}</span></li>}
    </ul>
  )
}
