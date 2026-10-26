import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { request, type DocumentPage } from '../api'

const POLL_MS = 8000

interface JobsValue {
  /** Documents waiting or being processed (state `uploaded` or `processing`). */
  active: number
  /** False after a failed request: the server cannot be reached. */
  reachable: boolean
  /** Checks now; call it after an upload so the indicator reacts at once. */
  refresh: () => void
}

const JobsContext = createContext<JobsValue | null>(null)

/**
 * Polls `GET /api/documents?state=uploaded,processing&limit=1` every 8 s, only while the tab is visible, and shares the
 * count with the top bar and the sidebar status chip.
 */
export function JobsProvider({ children }: { children: ReactNode }) {
  const [active, setActive] = useState(0)
  const [reachable, setReachable] = useState(true)
  const tickRef = useRef<() => void>(() => undefined)

  useEffect(() => {
    let timer: number | undefined
    let controller: AbortController | null = null
    let disposed = false

    const clear = () => {
      window.clearTimeout(timer)
      controller?.abort()
      controller = null
    }
    const schedule = () => {
      window.clearTimeout(timer)
      if (!disposed && document.visibilityState === 'visible') timer = window.setTimeout(() => void tick(), POLL_MS)
    }
    const tick = async () => {
      if (document.visibilityState !== 'visible') return
      controller?.abort()
      const mine = new AbortController()
      controller = mine
      try {
        const page = await request<DocumentPage>('/api/documents', { query: { state: 'uploaded,processing', limit: 1 }, signal: mine.signal })
        if (mine.signal.aborted) return
        setActive(page.total)
        setReachable(true)
      } catch {
        if (mine.signal.aborted) return
        setReachable(false)
      }
      schedule()
    }
    const onVisibility = () => {
      if (document.visibilityState === 'visible') void tick()
      else clear()
    }
    tickRef.current = () => void tick()
    document.addEventListener('visibilitychange', onVisibility)
    void tick()
    return () => {
      disposed = true
      document.removeEventListener('visibilitychange', onVisibility)
      clear()
    }
  }, [])

  const refresh = useCallback(() => tickRef.current(), [])
  const value = useMemo(() => ({ active, reachable, refresh }), [active, reachable, refresh])
  return <JobsContext.Provider value={value}>{children}</JobsContext.Provider>
}

/** Background-job state; must be used under `JobsProvider` (the shell provides it). */
export function useJobs(): JobsValue {
  const value = useContext(JobsContext)
  if (!value) throw new Error('useJobs must be used inside JobsProvider')
  return value
}
