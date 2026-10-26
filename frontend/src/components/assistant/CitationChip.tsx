import { useId, useState, type SyntheticEvent } from 'react'
import type { Citation } from '../../api/chat'
import { formatDate } from '../../lib/format'
import { Icon } from '../Icon'

/** Matches `.cite__pop` in assistant.css. */
const POP_WIDTH = 340

interface CitationChipProps {
  citation: Citation
  onOpen: (citation: Citation) => void
}

/** Source line "24/KH-PTM · 12/03/2026 · mục II". */
export function citationMeta(citation: Citation): string {
  return [citation.ref, citation.date ? formatDate(citation.date, '') : '', citation.section].filter(Boolean).join(' · ')
}

/**
 * The [n] marker inside an answer: a small square brass superscript that opens the source in the side panel. Hovering or
 * focusing it previews the cited passage; a source the user may no longer see is shown struck out and disabled.
 */
export function CitationChip({ citation, onOpen }: CitationChipProps) {
  const popId = useId()
  const [flip, setFlip] = useState(false)
  // Keep the preview inside the conversation: open it towards the left when the marker is near the right edge.
  const place = (event: SyntheticEvent<HTMLElement>) => {
    const host = event.currentTarget.closest('.thread')
    if (host) setFlip(event.currentTarget.getBoundingClientRect().left + POP_WIDTH > host.getBoundingClientRect().right - 12)
  }
  return (
    <span className={flip ? 'cite cite--flip' : 'cite'} onMouseEnter={place} onFocus={place}>
      <button
        type="button"
        className="cite__mark"
        disabled={!citation.readable}
        aria-describedby={popId}
        aria-label={`Nguồn ${citation.n}: ${citation.title}`}
        onClick={() => onOpen(citation)}
      >
        {citation.n}
      </button>
      <span className="cite__pop" role="tooltip" id={popId}>
        <span className="cite__pop-title">{citation.title || citation.ref}</span>
        <span className="cite__pop-meta">{[citationMeta(citation), citation.unit_name].filter(Boolean).join(' · ')}</span>
        {citation.readable ? (
          citation.text && <span className="cite__pop-text">{citation.text}</span>
        ) : (
          <span className="cite__pop-off"><Icon name="lock" size={14} />Bạn không còn quyền xem văn bản này.</span>
        )}
      </span>
    </span>
  )
}
