import { useCallback, useEffect, useRef, useState } from 'react'
import { spellCheckApi } from '../api'
import type { SpellSession } from '../api/spellCheck'
import { SpellInput } from '../components/spell/SpellInput'
import { SpellResultView } from '../components/spell/SpellResultView'
import { useDocumentTitle } from '../hooks/useDocumentTitle'

/**
 * "Kiểm tra chính tả": paste text or choose a file, see the doubtful words marked on the text and listed with a suggestion, tick the
 * ones to correct and download the result. The copy on the server is temporary and is deleted when the user starts over or leaves.
 */
export function SpellPage() {
  useDocumentTitle('Kiểm tra chính tả')
  const [session, setSession] = useState<SpellSession | null>(null)
  const currentId = useRef<string | null>(null)

  const change = useCallback((next: SpellSession | null) => {
    currentId.current = next?.id ?? null
    setSession(next)
  }, [])

  const reset = useCallback(() => {
    if (currentId.current) spellCheckApi.discardSession(currentId.current)
    change(null)
  }, [change])

  // Leaving the page (route change, tab close or reload) deletes the temporary copy.
  useEffect(() => {
    const discard = () => {
      if (currentId.current) spellCheckApi.discardSession(currentId.current)
    }
    window.addEventListener('pagehide', discard)
    return () => {
      window.removeEventListener('pagehide', discard)
      discard()
    }
  }, [])

  return session ? <SpellResultView key={session.id} session={session} onSessionChange={change} onReset={reset} /> : <SpellInput onChecked={change} />
}
