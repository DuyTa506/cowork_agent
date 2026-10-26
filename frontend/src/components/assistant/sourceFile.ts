import { useEffect, useState } from 'react'
import { documentsApi } from '../../api'

/** File names of store documents by id: the citation does not carry one, and the file-type badge needs the extension. */
const names = new Map<number, Promise<string>>()

function storeFileName(id: number): Promise<string> {
  let known = names.get(id)
  if (!known) {
    known = documentsApi.getDocument(id).then((document) => document.original_name).catch(() => {
      names.delete(id)
      return ''
    })
    names.set(id, known)
  }
  return known
}

/**
 * The file name of a cited source, for its file-type badge. Attachments are looked up in `attachmentNames`; documents in the
 * store are fetched once (and remembered). Empty while unknown.
 */
export function useSourceFileName(kind: 'store' | 'attachment', id: number | null, attachmentNames: ReadonlyMap<number, string>): string {
  const attachmentName = kind === 'attachment' && id !== null ? (attachmentNames.get(id) ?? '') : ''
  const [stored, setStored] = useState('')
  useEffect(() => {
    if (kind !== 'store' || id === null) return
    let cancelled = false
    void storeFileName(id).then((name) => {
      if (!cancelled) setStored(name)
    })
    return () => {
      cancelled = true
    }
  }, [kind, id])
  return kind === 'attachment' ? attachmentName : stored
}
