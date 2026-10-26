import { useState } from 'react'
import { chatApi } from '../../api'
import type { DocumentSummary } from '../../api'
import { Alert } from '../Alert'
import { Button } from '../Button'
import { Modal } from '../Modal'
import { Switch } from '../Switch'

interface SaveDraftDialogProps {
  sessionId: string
  title: string
  onClose: () => void
  onSaved: (document: DocumentSummary) => void
}

/** Saves the draft into Kho văn bản; the user declares whether it carries secret content. */
export function SaveDraftDialog({ sessionId, title, onClose, onSaved }: SaveDraftDialogProps) {
  const [secret, setSecret] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      onSaved(await chatApi.saveDraft(sessionId, secret))
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Không lưu được vào kho.')
      setBusy(false)
    }
  }

  return (
    <Modal
      title="Lưu vào Kho văn bản"
      size="sm"
      onClose={onClose}
      busy={busy}
      footer={
        <>
          <Button onClick={onClose} disabled={busy}>Hủy</Button>
          <Button variant="primary" icon="save" onClick={() => void save()} loading={busy} data-autofocus>Lưu vào kho</Button>
        </>
      }
    >
      <p>Bản dự thảo “{title}” sẽ được dựng thành tệp DOCX theo mẫu và lưu vào Kho văn bản của đơn vị bạn.</p>
      <Switch checked={secret} onChange={setSecret} label="Văn bản có nội dung mật" disabled={busy} />
      <p className="sub">Văn bản mật chỉ chỉ huy được xem. Nếu không chắc, hãy đánh dấu mật.</p>
      {error && <Alert kind="error">{error}</Alert>}
    </Modal>
  )
}
