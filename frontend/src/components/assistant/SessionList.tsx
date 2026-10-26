import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import type { ChatSession } from '../../api/chat'
import { Alert } from '../Alert'
import { Button } from '../Button'
import { ConfirmDialog } from '../ConfirmDialog'
import { Icon } from '../Icon'
import { Spinner } from '../Spinner'
import { dayGroup, GROUP_LABELS, shortWhen, type DayGroup } from './log'
import { PopMenu } from './PopMenu'

interface SessionListProps {
  sessions: ChatSession[]
  activeId: string | null
  loading: boolean
  error: string | null
  onSelect: (id: string) => void
  onNew: () => void
  onRename: (id: string, title: string) => Promise<void>
  onDelete: (id: string) => Promise<void>
  onReload: () => void
}

/** Title edited in place: Enter saves, Esc cancels. */
function RenameField({ session, onDone }: { session: ChatSession; onDone: (title: string | null) => void }) {
  const ref = useRef<HTMLInputElement>(null)
  const [value, setValue] = useState(session.title)
  const finished = useRef(false)
  useEffect(() => {
    ref.current?.focus()
    ref.current?.select()
  }, [])
  const finish = (title: string | null) => {
    if (finished.current) return
    finished.current = true
    onDone(title)
  }
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' && !event.nativeEvent.isComposing) finish(value.trim() || null)
    if (event.key === 'Escape') finish(null)
  }
  return (
    <input
      ref={ref}
      className="input sess__rename"
      aria-label="Tên cuộc trò chuyện"
      value={value}
      maxLength={120}
      onChange={(event) => setValue(event.target.value)}
      onKeyDown={onKeyDown}
      onBlur={() => finish(value.trim() || null)}
    />
  )
}

/** Left column: new conversation, search and the conversations grouped by day (Hôm nay · Tuần này · Cũ hơn). */
export function SessionList({ sessions, activeId, loading, error, onSelect, onNew, onRename, onDelete, onReload }: SessionListProps) {
  const [renaming, setRenaming] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<ChatSession | null>(null)
  const [failure, setFailure] = useState<string | null>(null)
  const [query, setQuery] = useState('')

  const finishRename = async (session: ChatSession, title: string | null) => {
    setRenaming(null)
    if (!title || title === session.title) return
    try {
      await onRename(session.id, title)
    } catch (problem) {
      setFailure(problem instanceof Error ? problem.message : 'Không đổi được tên.')
    }
  }

  const groups = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase('vi-VN')
    const shown = needle ? sessions.filter((session) => session.title.toLocaleLowerCase('vi-VN').includes(needle)) : sessions
    const buckets: Record<DayGroup, ChatSession[]> = { today: [], week: [], older: [] }
    for (const session of shown) buckets[dayGroup(session.updated_at)].push(session)
    return (['today', 'week', 'older'] as const).map((key) => ({ key, items: buckets[key] })).filter((group) => group.items.length > 0)
  }, [sessions, query])

  return (
    <nav className="sess" aria-label="Các cuộc trò chuyện">
      <div className="sess__top">
        <Button className="sess__new" icon="plus" onClick={onNew}>Cuộc trò chuyện mới</Button>
        <div className="sess__search">
          <Icon name="search" size={16} />
          <input
            type="search"
            aria-label="Tìm cuộc trò chuyện"
            placeholder="Tìm cuộc trò chuyện"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
      </div>
      <div className="sess__scroll">
        {failure && <Alert kind="error" action={<button type="button" className="btn" onClick={() => setFailure(null)}>Đóng</button>}>{failure}</Alert>}
        {loading && sessions.length === 0 && <div className="page-loading"><Spinner label="Đang tải danh sách" /></div>}
        {error && <Alert kind="error" action={<button type="button" className="btn" onClick={onReload}>Thử lại</button>}>{error}</Alert>}
        {!loading && !error && sessions.length === 0 && <p className="sess__empty">Chưa có cuộc trò chuyện nào. Câu hỏi đầu tiên sẽ tạo một cuộc trò chuyện.</p>}
        {!loading && !error && sessions.length > 0 && groups.length === 0 && <p className="sess__empty">Không có cuộc trò chuyện nào khớp “{query}”.</p>}
        {groups.map((group) => (
          <section key={group.key} className="sess__group" aria-label={GROUP_LABELS[group.key]}>
            <h2 className="sess__label section-label">{GROUP_LABELS[group.key]}</h2>
            <ul>
              {group.items.map((session) => {
                const active = session.id === activeId
                const title = session.title || 'Cuộc trò chuyện mới'
                return (
                  <li key={session.id} className={active ? 'sess__item sess__item--on' : 'sess__item'}>
                    {renaming === session.id ? (
                      <RenameField session={session} onDone={(next) => void finishRename(session, next)} />
                    ) : (
                      <>
                        <button type="button" className="sess__open" aria-current={active ? 'true' : undefined} onClick={() => onSelect(session.id)} title={title}>
                          <span className="sess__title">{title}</span>
                          <span className="sess__when tnum">{shortWhen(session.updated_at)}</span>
                        </button>
                        <PopMenu
                          label={`Tùy chọn: ${title}`}
                          width={208}
                          items={[
                            { key: 'rename', label: 'Đổi tên', icon: 'edit', onSelect: () => setRenaming(session.id) },
                            { key: 'delete', label: 'Xóa cuộc trò chuyện', icon: 'trash', danger: true, onSelect: () => setDeleting(session) },
                          ]}
                          trigger={(props) => (
                            <button {...props} type="button" className="sess__kebab" aria-label={`Tùy chọn cho “${title}”`} title="Đổi tên hoặc xóa">
                              <Icon name="more" size={20} />
                            </button>
                          )}
                        />
                      </>
                    )}
                  </li>
                )
              })}
            </ul>
          </section>
        ))}
      </div>
      {deleting && (
        <ConfirmDialog
          title="Xóa cuộc trò chuyện"
          confirmLabel="Xóa"
          danger
          onCancel={() => setDeleting(null)}
          onConfirm={async () => {
            await onDelete(deleting.id)
            setDeleting(null)
          }}
        >
          <p>Xóa cuộc trò chuyện “{deleting.title}” cùng các tin nhắn, tệp đính kèm và bản dự thảo của nó? Không thể hoàn tác.</p>
        </ConfirmDialog>
      )}
    </nav>
  )
}
