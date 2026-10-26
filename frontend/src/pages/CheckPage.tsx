import { useCallback, useEffect, useRef, useState } from 'react'
import { formatCheckApi } from '../api'
import type { CheckSession } from '../api/formatCheck'
import { CheckResultView } from '../components/check/CheckResultView'
import { CheckUpload } from '../components/check/CheckUpload'
import { useDocumentTitle } from '../hooks/useDocumentTitle'

/**
 * "Kiểm tra thể thức": choose a file, see its format and spelling findings, tick the fixes to apply and download the result.
 * The uploaded copy is temporary, so it is deleted from the server when the user picks another file or leaves the page.
 */
export function CheckPage() {
  useDocumentTitle('Kiểm tra thể thức')
  const [session, setSession] = useState<CheckSession | null>(null)
  const currentId = useRef<string | null>(null)

  const change = useCallback((next: CheckSession | null) => {
    currentId.current = next?.id ?? null
    setSession(next)
  }, [])

  const reset = useCallback(() => {
    if (currentId.current) formatCheckApi.discardCheck(currentId.current)
    change(null)
  }, [change])

  // Leaving the page (route change, tab close or reload) deletes the temporary file.
  useEffect(() => {
    const discard = () => {
      if (currentId.current) formatCheckApi.discardCheck(currentId.current)
    }
    window.addEventListener('pagehide', discard)
    return () => {
      window.removeEventListener('pagehide', discard)
      discard()
    }
  }, [])

  return session ? (
    <CheckResultView key={session.id} session={session} onSessionChange={change} onReset={reset} />
  ) : (
    <CheckUpload onChecked={change} />
  )
}
