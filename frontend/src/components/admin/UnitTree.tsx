import { useMemo, useState } from 'react'
import type { Unit } from '../../api'
import { Icon } from '../Icon'

interface UnitTreeProps {
  units: Unit[]
  /** Accounts per unit id. */
  counts: ReadonlyMap<string, number>
}

/** The organisation chart, folded: only the top unit shows at first and each branch opens on request. A folded branch shows the accounts of everything under it. */
export function UnitTree({ units, counts }: UnitTreeProps) {
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set())

  const { children, totals } = useMemo(() => {
    const kids = new Map<string, Unit[]>()
    for (const unit of units) kids.set(unit.parent, [...(kids.get(unit.parent) ?? []), unit])
    const sums = new Map<string, number>()
    const total = (unit: Unit): number => {
      const sum = (counts.get(unit.id) ?? 0) + (kids.get(unit.id) ?? []).reduce((acc, child) => acc + total(child), 0)
      sums.set(unit.id, sum)
      return sum
    }
    units.filter((unit) => unit.depth === 0).forEach(total)
    return { children: kids, totals: sums }
  }, [units, counts])

  const toggle = (id: string) => setOpen((current) => {
    const next = new Set(current)
    if (!next.delete(id)) next.add(id)
    return next
  })
  const branches = units.filter((unit) => (children.get(unit.id) ?? []).length > 0)
  const allOpen = branches.length > 0 && branches.every((unit) => open.has(unit.id))

  // The list is in depth-first order, so a unit is visible when every ancestor is open.
  const byId = new Map(units.map((unit) => [unit.id, unit]))
  const visible = units.filter((unit) => {
    for (let parent = byId.get(unit.parent); parent; parent = byId.get(parent.parent)) if (!open.has(parent.id)) return false
    return true
  })

  return (
    <>
      <div className="unit-tree__bar">
        <button type="button" className="unit-tree__all" onClick={() => setOpen(allOpen ? new Set() : new Set(branches.map((unit) => unit.id)))}>
          {allOpen ? 'Thu gọn tất cả' : 'Mở rộng tất cả'}
        </button>
      </div>
      <ul className="unit-tree">
        {visible.map((unit) => {
          const isBranch = (children.get(unit.id) ?? []).length > 0
          const expanded = open.has(unit.id)
          const count = expanded ? counts.get(unit.id) ?? 0 : totals.get(unit.id) ?? 0
          return (
            <li key={unit.id} style={{ paddingLeft: 8 + unit.depth * 16 }} className={unit.depth === 0 ? 'unit-tree__root' : undefined}>
              <span className="unit-tree__name">
                {isBranch ? (
                  <button type="button" className="unit-tree__twist" aria-expanded={expanded} aria-label={`${expanded ? 'Thu gọn' : 'Mở'} ${unit.name}`} onClick={() => toggle(unit.id)}>
                    <Icon name={expanded ? 'chevronDown' : 'chevronRight'} size={16} />
                  </button>
                ) : (
                  <span className="unit-tree__twist unit-tree__twist--leaf" aria-hidden="true" />
                )}
                {unit.name}
              </span>
              {count > 0 && <span className="unit-tree__count" title={expanded || !isBranch ? 'Số tài khoản' : 'Số tài khoản của cả nhánh'}>{count}</span>}
            </li>
          )
        })}
      </ul>
    </>
  )
}
