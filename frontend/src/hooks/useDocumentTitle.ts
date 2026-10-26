import { useEffect } from 'react'

const SUFFIX = 'Quân khu 3'

/** Sets the browser tab title for the current page. */
export function useDocumentTitle(title: string): void {
  useEffect(() => {
    document.title = `${title} · ${SUFFIX}`
  }, [title])
}
