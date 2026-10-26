import type { ChatDraft } from '../../api/chat'
import { formatDateTime } from '../../lib/format'
import { Chip } from '../Chip'

/** "Lịch sử": who changed the draft in each version, newest first. */
export function HistoryPanel({ draft }: { draft: ChatDraft }) {
  const entries = [...draft.history].sort((a, b) => b.version - a.version)
  if (entries.length === 0) return <p className="cv-side__none">Chưa có thay đổi nào.</p>
  return (
    <ol className="cv-hist">
      {entries.map((entry) => (
        <li key={entry.version} className={entry.by === 'assistant' ? 'cv-hist__item cv-hist__item--ai' : 'cv-hist__item'}>
          <div className="cv-hist__head">
            <b className="tnum">Phiên bản {entry.version}</b>
            <Chip tone={entry.by === 'assistant' ? 'amber' : 'blue'} icon={entry.by === 'assistant' ? 'canvas' : 'user'}>{entry.by === 'assistant' ? 'Trợ lý' : 'Đồng chí'}</Chip>
          </div>
          <time className="cv-hist__time tnum">{formatDateTime(entry.at)}</time>
          <p className="cv-hist__sum">{entry.summary}</p>
        </li>
      ))}
    </ol>
  )
}
