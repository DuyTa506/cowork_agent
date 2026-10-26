import { useCallback, useEffect, useRef, useState, type DependencyList } from 'react'

export interface AsyncData<T> {
  /** Last successfully loaded value; kept while a reload is in flight. */
  data: T | null
  error: Error | null
  loading: boolean
  /** Loads again (the old data stays visible meanwhile). */
  reload: () => void
  /** Replaces the data without a request, for example with the response of a save. */
  setData: (data: T) => void
}

export interface AsyncOptions<T> {
  /** Poll interval in milliseconds. */
  pollMs?: number
  /** Polling continues only while this returns true for the latest data. */
  shouldPoll?: (data: T) => boolean
}

interface State<T> {
  data: T | null
  error: Error | null
  loading: boolean
}

/**
 * Loads data when `deps` change and, optionally, keeps refreshing it silently while `shouldPoll` holds.
 * Stale responses are discarded and in-flight requests are aborted when the inputs change or the component unmounts.
 */
export function useAsyncData<T>(
  load: (signal: AbortSignal) => Promise<T>,
  deps: DependencyList,
  options: AsyncOptions<T> = {},
): AsyncData<T> {
  const [state, setState] = useState<State<T>>({ data: null, error: null, loading: true })
  const [version, setVersion] = useState(0)
  const loadRef = useRef(load)
  const optionsRef = useRef(options)
  useEffect(() => {
    loadRef.current = load
    optionsRef.current = options
  })

  useEffect(() => {
    const controller = new AbortController()
    let timer: number | undefined

    const schedule = (data: T | null) => {
      const { pollMs, shouldPoll } = optionsRef.current
      if (pollMs && data !== null && shouldPoll?.(data)) timer = window.setTimeout(() => void run(true, data), pollMs)
    }

    const run = async (silent: boolean, previous: T | null) => {
      if (!silent) setState((current) => ({ ...current, loading: true, error: null }))
      try {
        const data = await loadRef.current(controller.signal)
        if (controller.signal.aborted) return
        setState({ data, error: null, loading: false })
        schedule(data)
      } catch (error) {
        if (controller.signal.aborted) return
        if (silent) {
          schedule(previous) // a failed background refresh keeps the old data and tries again
          return
        }
        setState((current) => ({ ...current, loading: false, error: error instanceof Error ? error : new Error(String(error)) }))
      }
    }

    void run(false, null)
    return () => {
      controller.abort()
      window.clearTimeout(timer)
    }
    // `load` is read through a ref; the caller lists everything it depends on in `deps`.
  }, [...deps, version])

  const reload = useCallback(() => setVersion((value) => value + 1), [])
  const setData = useCallback((data: T) => setState({ data, error: null, loading: false }), [])
  return { ...state, reload, setData }
}
