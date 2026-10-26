import { createContext, useContext, useMemo, type ReactNode } from 'react'
import { unitsApi, type Unit } from '../api'
import { useAsyncData } from './useAsyncData'

interface UnitsValue {
  /** The organisation chart in display order (depth-first), with `depth` for indentation. */
  units: Unit[]
  byId: ReadonlyMap<string, Unit>
  loading: boolean
  error: Error | null
}

const UnitsContext = createContext<UnitsValue | null>(null)

/** Loads the organisation chart once for the signed-in session and shares it with filters and forms. */
export function UnitsProvider({ children }: { children: ReactNode }) {
  const { data, loading, error } = useAsyncData((signal) => unitsApi.listUnits(signal), [])
  const value = useMemo<UnitsValue>(() => {
    const units = data ?? []
    return { units, byId: new Map(units.map((unit) => [unit.id, unit])), loading, error }
  }, [data, loading, error])
  return <UnitsContext.Provider value={value}>{children}</UnitsContext.Provider>
}

/** The organisation chart; must be used under `UnitsProvider`. */
export function useUnits(): UnitsValue {
  const value = useContext(UnitsContext)
  if (!value) throw new Error('useUnits must be used inside UnitsProvider')
  return value
}
