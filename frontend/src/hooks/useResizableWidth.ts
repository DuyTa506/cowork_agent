import { useCallback, useEffect, useState } from 'react'
import { readStorage, writeStorage } from '../lib/storage'

export interface ResizableWidth {
  width: number
  /** Sets the width (clamped) and remembers it. */
  set: (value: number) => void
  reset: () => void
  min: number
  max: number
}

/** A panel width the user can drag: clamped to [min, max], remembered in localStorage under `storageKey`. */
export function useResizableWidth(storageKey: string, initial: number, min: number, max: number): ResizableWidth {
  const clamp = useCallback((value: number) => Math.min(max, Math.max(min, Math.round(value))), [min, max])
  const [width, setWidth] = useState(() => {
    const stored = Number(readStorage('local', storageKey))
    return Number.isFinite(stored) && stored > 0 ? Math.min(max, Math.max(min, stored)) : initial
  })
  useEffect(() => setWidth((current) => clamp(current)), [clamp])
  const set = useCallback((value: number) => {
    const next = clamp(value)
    setWidth(next)
    writeStorage('local', storageKey, String(next))
  }, [clamp, storageKey])
  const reset = useCallback(() => {
    setWidth(initial)
    writeStorage('local', storageKey, String(initial))
  }, [initial, storageKey])
  return { width, set, reset, min, max }
}
