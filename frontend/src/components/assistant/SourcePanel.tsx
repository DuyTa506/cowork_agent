import { useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { chatApi } from '../../api'
import { Button } from '../Button'
import { DocumentView } from '../DocumentView'
import { FileTypeBadge } from '../FileTypeBadge'
import { Icon } from '../Icon'
import { useSourceFileName } from './sourceFile'
import type { SourceRef } from './types'

interface SourcePanelProps {
  source: SourceRef
  sessionId: string
  attachmentNames: ReadonlyMap<number, string>
  onSummarize: (source: SourceRef) => void
  /** Disabled while a turn is running. */
  busy: boolean
}

/** A cited document next to the chat: header with its type and numbers, the cited passage, then the text with the passage marked. */
export function SourcePanel({ source, sessionId, attachmentNames, onSummarize, busy }: SourcePanelProps) {
  const from = source.pi?.[0]
  const to = source.pi?.[1]
  const highlight = useMemo(() => (from !== undefined && to !== undefined ? { from, to } : undefined), [from, to])
  const fileName = useSourceFileName(source.kind, source.id, attachmentNames)
  const load = useCallback(
    (signal: AbortSignal) => chatApi.getSourceContent({ kind: source.kind, docId: source.id }, sessionId, signal),
    [source.kind, source.id, sessionId],
  )

  return (
    <div className="src">
      <header className="src__head">
        <FileTypeBadge name={fileName} size="md" />
        <div className="src__id">
          <span className="src__where section-label">{source.kind === 'store' ? 'Kho văn bản' : 'Tệp đính kèm'}</span>
          <h2 className="src__title">{source.title || source.ref}</h2>
          <p className="src__meta tnum">{[source.ref, fileName].filter(Boolean).join(' · ')}</p>
        </div>
      </header>
      {source.n !== null && (
        <div className="src__cite">
          <span className="cite__mark cite__mark--static" aria-hidden="true">{source.n}</span>
          <div>
            <span className="src__cite-label">Đoạn được trích dẫn{source.section ? ` · ${source.section}` : ''}</span>
            {source.text && <p className="src__cite-text">{source.text}</p>}
            {!source.pi && <p className="src__cite-note"><Icon name="info" size={14} />Không xác định được đoạn cụ thể trong văn bản; xem toàn văn bên dưới.</p>}
          </div>
        </div>
      )}
      <DocumentView key={`${sessionId}:${source.key}`} className="src__viewer" documentId={source.id} highlight={highlight} loadContent={load} snippet={source.text} tryPages={source.kind === 'store'} />
      <footer className="src__foot">
        {source.kind === 'store' && (
          <Link className="btn" to={`/kho/${source.id}`}>
            <Icon name="externalLink" size={16} />
            Mở trong Kho văn bản
          </Link>
        )}
        <Button icon="clipboard" disabled={busy} onClick={() => onSummarize(source)}>Tóm tắt văn bản này</Button>
      </footer>
    </div>
  )
}
