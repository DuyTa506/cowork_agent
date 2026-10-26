import { useCallback, useEffect, useMemo, useState } from 'react'

/** The reveal takes about 25 ms per group of words and never longer than MAX_MS in total. */
const TICK_MS = 28
const MAX_MS = 1800
const GROUP = 2

const prefersReducedMotion = (): boolean => window.matchMedia('(prefers-reduced-motion: reduce)').matches

/** Offsets just after each run of whitespace: the places where the text may be cut without splitting a word. */
function wordEnds(text: string): number[] {
  const ends: number[] = []
  for (const match of text.matchAll(/\s+/g)) ends.push((match.index ?? 0) + match[0].length)
  ends.push(text.length)
  return ends
}

/**
 * Shows `text` progressively by groups of words (the server delivers an answer whole, after its steps). Disabled for stored
 * answers, and instant under reduced motion. `skip()` shows everything at once (click on the answer).
 */
export function useReveal(text: string, enabled: boolean): { shown: string; done: boolean; skip: () => void } {
  const instant = !enabled || prefersReducedMotion()
  const ends = useMemo(() => wordEnds(text), [text])
  const [count, setCount] = useState(0)
  const [skipped, setSkipped] = useState(false)

  useEffect(() => {
    setCount(0)
    setSkipped(false)
  }, [text])

  useEffect(() => {
    if (instant || skipped || text.length === 0) return
    const step = Math.max(GROUP, Math.ceil(ends.length / (MAX_MS / TICK_MS)))
    const timer = window.setInterval(() => {
      setCount((current) => {
        const next = current + step
        if (next >= ends.length) window.clearInterval(timer)
        return Math.min(next, ends.length)
      })
    }, TICK_MS)
    return () => window.clearInterval(timer)
  }, [text, ends, instant, skipped])

  const skip = useCallback(() => setSkipped(true), [])

  if (instant || skipped || text.length === 0) return { shown: text, done: true, skip }
  const visible = count >= ends.length ? text.length : count === 0 ? 0 : (ends[count - 1] ?? 0)
  return { shown: text.slice(0, visible), done: visible >= text.length, skip }
}
