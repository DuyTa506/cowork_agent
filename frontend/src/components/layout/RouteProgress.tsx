import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'

type Phase = 'idle' | 'run' | 'done'

/** Thin bar under the top edge that runs while the route changes (the page chunk loads) and completes when it has rendered. */
export function RouteProgress() {
  const { pathname } = useLocation()
  const [phase, setPhase] = useState<Phase>('idle')
  const first = useRef(true)

  useEffect(() => {
    if (first.current) {
      first.current = false
      return
    }
    setPhase('run')
    const finish = window.setTimeout(() => setPhase('done'), 420)
    const reset = window.setTimeout(() => setPhase('idle'), 900)
    return () => {
      window.clearTimeout(finish)
      window.clearTimeout(reset)
    }
  }, [pathname])

  return (
    <div className={`route-progress route-progress--${phase}`} role="presentation" aria-hidden="true">
      <div className="route-progress__bar" />
    </div>
  )
}
