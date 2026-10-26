import { useId, useState } from 'react'
import { Link } from 'react-router-dom'
import { formatCheckApi, type DocumentSummary } from '../../api'
import type { SaveWhich } from '../../api/formatCheck'
import { Button } from '../Button'
import { FileTypeBadge } from '../FileTypeBadge'
import { Icon } from '../Icon'
import { Modal } from '../Modal'
import { describeFailure, type FailureText } from './model'
import { FailureNotice, Notice } from './Notice'

interface SaveToStoreDialogProps {
  checkId: string
  /** Name of the checked file. */
  fileName: string
  /** A corrected copy exists. */
  hasFixed: boolean
  onClose: () => void
}

/** Puts the checked file (original or corrected) into the document store, where it is processed like any upload. */
export function SaveToStoreDialog({ checkId, fileName, hasFixed, onClose }: SaveToStoreDialogProps) {
  const name = useId()
  const [which, setWhich] = useState<SaveWhich>(hasFixed ? 'fixed' : 'original')
  const [secret, setSecret] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<FailureText | null>(null)
  const [saved, setSaved] = useState<DocumentSummary | null>(null)

  const fixedName = formatCheckApi.downloadName({ name: fileName }, 'fixed')

  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      setSaved(await formatCheckApi.saveToStore(checkId, which, secret))
    } catch (failure) {
      setError(describeFailure(failure, 'Không lưu được vào kho'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      title="Lưu vào kho văn bản"
      size="md"
      onClose={onClose}
      busy={busy}
      footer={
        saved ? (
          <Button variant="primary" onClick={onClose} data-autofocus>Đóng</Button>
        ) : (
          <>
            <Button onClick={onClose} disabled={busy}>Hủy</Button>
            <Button variant="primary" icon="folder" onClick={save} loading={busy}>Lưu vào kho</Button>
          </>
        )
      }
    >
      {saved ? (
        <Notice tone="success" icon="checkCircle" title="Đã đưa vào kho văn bản">
          <p>“{saved.original_name}” đang được xử lý và lập chỉ mục.</p>
          <p><Link to={`/kho/${saved.id}`} onClick={onClose}>Mở văn bản</Link></p>
        </Notice>
      ) : (
        <>
          <p className="check-save__lead">Tệp sẽ được xử lý và lập chỉ mục như một văn bản tải lên kho.</p>
          <fieldset className="check-choice">
            <legend className="check-field__label">Bản cần lưu</legend>
            <label className={['check-opt', which === 'fixed' && 'check-opt--on', !hasFixed && 'check-opt--off'].filter(Boolean).join(' ')}>
              <input type="radio" name={name} checked={which === 'fixed'} disabled={!hasFixed} onChange={() => setWhich('fixed')} />
              <FileTypeBadge name={fixedName} size="sm" />
              <span className="check-opt__text">
                <strong>Bản đã sửa</strong>
                <span>{hasFixed ? fixedName : 'Chưa có: hãy chọn mục và bấm “Sửa” trước.'}</span>
              </span>
            </label>
            <label className={['check-opt', which === 'original' && 'check-opt--on'].filter(Boolean).join(' ')}>
              <input type="radio" name={name} checked={which === 'original'} onChange={() => setWhich('original')} />
              <FileTypeBadge name={fileName} size="sm" />
              <span className="check-opt__text">
                <strong>Bản gốc</strong>
                <span>{fileName}</span>
              </span>
            </label>
          </fieldset>
          <label className={['check-opt', 'check-opt--secret', secret && 'check-opt--on'].filter(Boolean).join(' ')}>
            <input type="checkbox" checked={secret} disabled={busy} onChange={(event) => setSecret(event.target.checked)} />
            <Icon name="lock" size={20} />
            <span className="check-opt__text">
              <strong>Đánh dấu văn bản mật</strong>
              <span>Văn bản mật chỉ chỉ huy được xem trong kho. Văn bản có dấu độ mật in trên đầu trang cũng được tự động đánh dấu mật.</span>
            </span>
          </label>
          {error && <FailureNotice failure={error} />}
        </>
      )}
    </Modal>
  )
}
