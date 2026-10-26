import { useId, useState } from 'react'
import { chatApi } from '../../api'
import type { Citation } from '../../api/chat'
import { formatDate } from '../../lib/format'
import { FileTypeBadge } from '../FileTypeBadge'
import { Icon } from '../Icon'
import { useSourceFileName } from './sourceFile'

interface SourceCardsProps {
  citations: Citation[]
  attachmentNames: ReadonlyMap<number, string>
  onOpen: (citation: Citation) => void
}

function SourceCard({ citation, attachmentNames, onOpen }: { citation: Citation; attachmentNames: ReadonlyMap<number, string>; onOpen: (citation: Citation) => void }) {
  const id = chatApi.attachmentIdOf(citation.doc_id)
  const fileName = useSourceFileName(citation.kind, id, attachmentNames)
  const meta = [citation.ref, citation.unit_name].filter(Boolean).join(' · ')
  const detail = [citation.doc_type, citation.date ? formatDate(citation.date, '') : '', citation.section].filter(Boolean).join(' · ')
  return (
    <li>
      <button
        type="button"
        className={citation.readable ? 'srcs__card' : 'srcs__card srcs__card--off'}
        disabled={!citation.readable}
        onClick={() => onOpen(citation)}
        aria-label={citation.readable ? `Mở nguồn ${citation.n}: ${citation.title}` : `Nguồn ${citation.n}: không còn quyền xem`}
      >
        <span className="srcs__n" aria-hidden="true">{citation.n}</span>
        <span className="srcs__badge">
          {citation.readable ? <FileTypeBadge name={fileName} size="md" /> : <Icon name="lock" size={20} />}
        </span>
        <span className="srcs__text">
          <span className="srcs__title">{citation.title || citation.ref}</span>
          {citation.readable ? (
            <>
              {meta && <span className="srcs__meta tnum">{meta}</span>}
              {detail && <span className="srcs__detail">{detail}</span>}
            </>
          ) : (
            <span className="srcs__meta">Không còn quyền xem văn bản này</span>
          )}
        </span>
        {citation.readable && <Icon name="chevronRight" size={16} className="srcs__go" />}
      </button>
    </li>
  )
}

const PREVIEW = 6

/**
 * "Nguồn trích dẫn": folded to one line under the answer (a count and the first source numbers); a click on it opens one numbered
 * card per cited document, and a click on a card opens the source with the passage marked.
 */
export function SourceCards({ citations, attachmentNames, onOpen }: SourceCardsProps) {
  const [open, setOpen] = useState(false)
  const listId = useId()
  return (
    <section className="srcs" aria-label="Nguồn trích dẫn">
      <button type="button" className="srcs__toggle" aria-expanded={open} aria-controls={listId} onClick={() => setOpen((value) => !value)}>
        <Icon name={open ? 'chevronUp' : 'chevronDown'} size={16} />
        <span className="srcs__count">{citations.length} nguồn trích dẫn</span>
        {!open && (
          <span className="srcs__peek" aria-hidden="true">
            {citations.slice(0, PREVIEW).map((citation) => <span key={citation.n} className="srcs__n srcs__n--sm">{citation.n}</span>)}
            {citations.length > PREVIEW && <span className="srcs__more tnum">+{citations.length - PREVIEW}</span>}
          </span>
        )}
      </button>
      {open && (
        <ol className="srcs__list" id={listId}>
          {citations.map((citation) => (
            <SourceCard key={citation.n} citation={citation} attachmentNames={attachmentNames} onOpen={onOpen} />
          ))}
        </ol>
      )}
    </section>
  )
}
