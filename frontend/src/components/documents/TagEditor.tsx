import { useId, useState } from 'react'
import { documentsApi, type DocumentDetail } from '../../api'
import { Button } from '../Button'
import { Icon } from '../Icon'
import { useToast } from '../Toast'

interface TagEditorProps {
  document: DocumentDetail
  /** Tags used in the store, for suggestions. */
  suggestions: string[]
  onSaved: (document: DocumentDetail) => void
}

const MAX_MANUAL = 12
const MAX_LENGTH = 40

/** Tags of a document: the computed ones (year, topic, scan) are fixed; the uploader and administrators add and remove their own. */
export function TagEditor({ document, suggestions, onSaved }: TagEditorProps) {
  const notify = useToast()
  const listId = useId()
  const [manual, setManual] = useState(document.manual_tags)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const computed = document.tags.filter((tag) => !document.manual_tags.includes(tag))
  const dirty = manual.join('\n') !== document.manual_tags.join('\n')
  const editable = document.can_manage

  const add = (raw: string) => {
    const tag = raw.replace(/[,\s]+/g, ' ').trim()
    if (!tag) return
    if (tag.length > MAX_LENGTH) { notify(`Thẻ dài quá ${MAX_LENGTH} ký tự.`, 'error'); return }
    if (manual.length >= MAX_MANUAL) { notify(`Mỗi văn bản chỉ gắn tối đa ${MAX_MANUAL} thẻ tự đặt.`, 'error'); return }
    if (![...manual, ...computed].some((have) => have.toLowerCase() === tag.toLowerCase())) setManual([...manual, tag])
    setDraft('')
  }

  const save = async () => {
    setSaving(true)
    try {
      onSaved(await documentsApi.setTags(document.id, manual))
      notify('Đã lưu thẻ.')
    } catch (failure) {
      notify(failure instanceof Error ? failure.message : 'Không lưu được thẻ.', 'error')
    } finally {
      setSaving(false)
    }
  }

  const offer = suggestions.filter((tag) => !manual.includes(tag) && !computed.includes(tag) && (!draft || tag.toLowerCase().includes(draft.toLowerCase()))).slice(0, 8)

  return (
    <section className="dgroup tagedit" aria-label="Thẻ">
      <h3 className="dgroup__title section-label">Thẻ</h3>
      <ul className="tagrow tagrow--wrap">
        {computed.map((tag) => <li key={tag}><span className="tagchip tagchip--auto" title="Thẻ do hệ thống tự gắn">{tag}</span></li>)}
        {manual.map((tag) => (
          <li key={tag}>
            <span className="tagchip tagchip--manual">
              {tag}
              {editable && <button type="button" className="tagchip__x" aria-label={`Bỏ thẻ ${tag}`} onClick={() => setManual(manual.filter((t) => t !== tag))}><Icon name="close" size={12} /></button>}
            </span>
          </li>
        ))}
        {computed.length + manual.length === 0 && <li className="muted tagedit__none">Chưa có thẻ nào.</li>}
      </ul>
      {editable && (
        <>
          <div className="tagedit__add">
            <input
              className="input"
              list={listId}
              value={draft}
              maxLength={MAX_LENGTH + 10}
              placeholder="Thêm thẻ rồi nhấn Enter"
              aria-label="Thêm thẻ"
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ',') { event.preventDefault(); add(draft) } }}
            />
            <Button icon="plus" onClick={() => add(draft)} disabled={!draft.trim()}>Thêm</Button>
          </div>
          <datalist id={listId}>{offer.map((tag) => <option key={tag} value={tag} />)}</datalist>
          {offer.length > 0 && (
            <div className="tagedit__suggest" aria-label="Gợi ý thẻ">
              {offer.slice(0, 6).map((tag) => <button key={tag} type="button" className="tagchip tagchip--suggest" onClick={() => add(tag)}><Icon name="plus" size={12} />{tag}</button>)}
            </div>
          )}
          {dirty && <div className="tagedit__save"><Button variant="primary" onClick={save} loading={saving}>Lưu thẻ</Button><Button variant="ghost" onClick={() => setManual(document.manual_tags)} disabled={saving}>Hoàn tác</Button></div>}
          <p className="tagedit__note">Thẻ có viền liền do hệ thống gắn theo năm, chủ đề và bản scan nên không sửa được; thẻ tự đặt có nút bỏ.</p>
        </>
      )}
    </section>
  )
}
