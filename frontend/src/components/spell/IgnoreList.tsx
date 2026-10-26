import { useState, type FormEvent } from 'react'
import { Button } from '../Button'
import { Icon } from '../Icon'

interface IgnoreListProps {
  words: string[]
  busy: boolean
  disabled: boolean
  /** The complete new list. */
  onChange: (words: string[]) => void
}

/** The words this session skips (case does not matter): added with "Bỏ qua" on a row or typed here, removed one by one. */
export function IgnoreList({ words, busy, disabled, onChange }: IgnoreListProps) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState('')

  const add = (event: FormEvent) => {
    event.preventDefault()
    const word = draft.trim()
    if (!word || disabled) return
    setDraft('')
    onChange([...words, word])
  }

  return (
    <div className="spell-ignore">
      <button type="button" className="spell-ignore__toggle" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
        <Icon name="eyeOff" size={16} />
        <span>Từ bỏ qua{words.length > 0 ? ` (${words.length})` : ''}</span>
        <Icon name={open ? 'chevronUp' : 'chevronDown'} size={16} />
      </button>
      {open && (
        <div className="spell-ignore__body">
          <p className="spell-ignore__help">Những từ này không bị báo lại trong lần soát này (tên riêng, thuật ngữ, viết tắt). Danh sách mất khi bạn rời màn này.</p>
          {words.length > 0 && (
            <ul className="spell-ignore__list" aria-label="Các từ đang bỏ qua">
              {words.map((word) => (
                <li key={word} className="spell-ignore__item">
                  <span>{word}</span>
                  <button type="button" aria-label={`Không bỏ qua “${word}” nữa`} title="Báo lại từ này" disabled={disabled} onClick={() => onChange(words.filter((entry) => entry !== word))}>
                    <Icon name="close" size={14} />
                  </button>
                </li>
              ))}
            </ul>
          )}
          <form className="spell-ignore__add" onSubmit={add}>
            <input className="input" placeholder="Thêm từ cần bỏ qua" aria-label="Thêm từ cần bỏ qua" value={draft} maxLength={80} disabled={disabled} onChange={(event) => setDraft(event.target.value)} />
            <Button type="submit" icon="plus" disabled={disabled || !draft.trim()} loading={busy}>Thêm</Button>
            {words.length > 0 && <Button variant="ghost" disabled={disabled} onClick={() => onChange([])}>Xóa danh sách</Button>}
          </form>
        </div>
      )}
    </div>
  )
}
