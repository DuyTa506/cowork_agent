import { useEffect, useId, useRef, useState, type DragEvent } from 'react'
import { Link } from 'react-router-dom'
import { documentsApi, type UploadItem } from '../../api'
import { formatFileSize } from '../../lib/format'
import { Alert } from '../Alert'
import { Button } from '../Button'
import { Chip } from '../Chip'
import { FileTypeBadge } from '../FileTypeBadge'
import { Icon } from '../Icon'
import { IconButton } from '../IconButton'
import { Modal } from '../Modal'

const ACCEPTED = ['.doc', '.docx', '.pdf']

interface UploadDialogProps {
  onClose: () => void
  /** Called as soon as the server has answered, so the list can show the new documents. */
  onUploaded: () => void
  /** Opens the file chooser immediately ("Tải nhiều tệp"). */
  pickOnOpen?: boolean
}

type Phase = 'select' | 'uploading' | 'done'

const hasAcceptedExtension = (name: string) => ACCEPTED.some((extension) => name.toLowerCase().endsWith(extension))
const sameFile = (a: File, b: File) => a.name === b.name && a.size === b.size && a.lastModified === b.lastModified

/**
 * Upload of one or more .doc/.docx/.pdf files by choosing or dropping them. Each chosen file gets a row (type badge, name, size,
 * state chip); the server accepts or rejects files individually, and duplicates link to the existing document.
 */
export function UploadDialog({ onClose, onUploaded, pickOnOpen = false }: UploadDialogProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const secretId = useId()
  const [files, setFiles] = useState<File[]>([])
  const [rejected, setRejected] = useState<string[]>([])
  const [secret, setSecret] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [phase, setPhase] = useState<Phase>('select')
  const [progress, setProgress] = useState(0)
  const [results, setResults] = useState<UploadItem[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (pickOnOpen) inputRef.current?.click()
  }, [pickOnOpen])

  const addFiles = (incoming: FileList | File[]) => {
    const list = Array.from(incoming)
    setRejected(list.filter((file) => !hasAcceptedExtension(file.name)).map((file) => file.name))
    const accepted = list.filter((file) => hasAcceptedExtension(file.name))
    setFiles((current) => [...current, ...accepted.filter((file) => !current.some((existing) => sameFile(existing, file)))])
    setError(null)
  }

  const onDrop = (event: DragEvent) => {
    event.preventDefault()
    setDragging(false)
    if (phase === 'select') addFiles(event.dataTransfer.files)
  }

  const start = async () => {
    setPhase('uploading')
    setProgress(0)
    setError(null)
    try {
      const result = await documentsApi.uploadDocuments(files, secret, setProgress)
      setResults(result.items)
      setPhase('done')
      onUploaded()
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Không tải lên được.')
      setPhase('select')
    }
  }

  const reset = () => {
    setFiles([])
    setResults([])
    setRejected([])
    setSecret(false)
    setPhase('select')
  }

  const uploading = phase === 'uploading'
  const sentAll = uploading && progress >= 1
  const percent = Math.round(progress * 100)

  return (
    <Modal
      title="Tải văn bản lên"
      size="lg"
      onClose={onClose}
      busy={uploading}
      footer={
        phase === 'done' ? (
          <>
            <Button onClick={reset}>Tải thêm tệp</Button>
            <Button variant="primary" onClick={onClose}>Đóng</Button>
          </>
        ) : (
          <>
            <Button onClick={onClose} disabled={uploading}>Hủy</Button>
            <Button variant="primary" icon="upload" onClick={start} loading={uploading} disabled={files.length === 0}>
              {files.length > 1 ? `Tải lên ${files.length} tệp` : 'Tải lên'}
            </Button>
          </>
        )
      }
    >
      {phase !== 'done' && (
        <>
          <div
            className={['updrop', dragging && 'updrop--over', files.length > 0 && 'updrop--compact'].filter(Boolean).join(' ')}
            role="button"
            tabIndex={0}
            aria-label="Chọn tệp hoặc kéo thả tệp vào đây"
            aria-disabled={uploading}
            onClick={() => !uploading && inputRef.current?.click()}
            onKeyDown={(event) => {
              if ((event.key === 'Enter' || event.key === ' ') && !uploading) {
                event.preventDefault()
                inputRef.current?.click()
              }
            }}
            onDragOver={(event) => { event.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
          >
            <span className="updrop__badges" aria-hidden="true">
              <FileTypeBadge name="x.docx" size={files.length > 0 ? 'sm' : 'md'} />
              <FileTypeBadge name="x.doc" size={files.length > 0 ? 'sm' : 'md'} />
              <FileTypeBadge name="x.pdf" size={files.length > 0 ? 'sm' : 'md'} />
            </span>
            <span className="updrop__text">
              <strong>{dragging ? 'Thả tệp để thêm vào danh sách' : files.length > 0 ? 'Kéo thả hoặc bấm để thêm tệp' : 'Kéo thả tệp vào đây hoặc bấm để chọn'}</strong>
              <span className="sub">Nhận tệp Word (.docx, .doc) và PDF, có thể chọn nhiều tệp cùng lúc.</span>
            </span>
            <input
              ref={inputRef}
              type="file"
              multiple
              hidden
              accept={ACCEPTED.join(',')}
              onChange={(event) => {
                if (event.target.files) addFiles(event.target.files)
                event.target.value = ''
              }}
            />
          </div>

          {rejected.length > 0 && (
            <Alert kind="warning" title="Bỏ qua tệp không đúng định dạng">{rejected.join(', ')}</Alert>
          )}

          {files.length > 0 && (
            <ul className="upfiles" aria-label="Tệp đã chọn">
              {files.map((file) => (
                <li key={`${file.name}-${file.size}-${file.lastModified}`} className="upfile">
                  <FileTypeBadge name={file.name} size="md" />
                  <div className="upfile__main">
                    <span className="upfile__name" title={file.name}>{file.name}</span>
                    <span className="upfile__sub tnum">{formatFileSize(file.size)}</span>
                    {uploading && (
                      <span className="upbar" role="progressbar" aria-label={`Tiến độ tải ${file.name}`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}>
                        <span className="upbar__fill" style={{ width: `${percent}%` }} />
                      </span>
                    )}
                  </div>
                  {uploading ? (
                    <Chip tone="blue" icon="spinner" busy>{sentAll ? 'Đang lưu' : `Đang tải ${percent}%`}</Chip>
                  ) : (
                    <>
                      <Chip tone="grey" icon="clock">Chờ tải lên</Chip>
                      <IconButton icon="close" label={`Bỏ ${file.name}`} size={18} onClick={() => setFiles((current) => current.filter((item) => item !== file))} />
                    </>
                  )}
                </li>
              ))}
            </ul>
          )}

          <label className={secret ? 'secretbox secretbox--on' : 'secretbox'} htmlFor={secretId}>
            <input id={secretId} type="checkbox" checked={secret} disabled={uploading} onChange={(event) => setSecret(event.target.checked)} />
            <Icon name="lock" size={20} weight="fill" className="secretbox__icon" />
            <span className="secretbox__text">
              <strong>Đánh dấu văn bản mật</strong>
              <span className="sub">
                Văn bản mật chỉ chỉ huy được xem. Nếu bạn là người dùng thường, bạn sẽ không còn thấy văn bản này trong kho
                sau khi hệ thống xử lý xong. Văn bản có dấu độ mật in trên đầu trang cũng được tự động đánh dấu mật.
              </span>
            </span>
          </label>

          {uploading && (
            <p className="upstatus" role="status">
              {sentAll ? 'Đã gửi xong, đang lưu và đưa vào hàng đợi xử lý…' : `Đang tải lên ${files.length} tệp… ${percent}%`}
            </p>
          )}
          {error && <Alert kind="error" title="Tải lên thất bại">{error}</Alert>}
        </>
      )}

      {phase === 'done' && <UploadResults items={results} files={files} onNavigate={onClose} />}
    </Modal>
  )
}

function UploadResults({ items, files, onNavigate }: { items: UploadItem[]; files: File[]; onNavigate: () => void }) {
  const ok = items.filter((item) => item.document).length
  const duplicates = items.filter((item) => !item.document && item.code === 'duplicate').length
  const failed = items.length - ok - duplicates
  const sizes = new Map(files.map((file) => [file.name, file.size]))
  return (
    <div className="upresults">
      <p className="upsummary" role="status">
        <strong className="tnum">{ok}/{items.length}</strong> tệp đã được nhận
        {duplicates > 0 && <> · <span className="tnum">{duplicates}</span> trùng lặp</>}
        {failed > 0 && <> · <span className="tnum">{failed}</span> lỗi</>}.
        {ok > 0 && ' Văn bản đang được xử lý, trạng thái cập nhật trong danh sách.'}
      </p>
      <ul className="upfiles" aria-label="Kết quả tải lên">
        {items.map((item, index) => {
          const size = sizes.get(item.name)
          const duplicate = !item.document && item.code === 'duplicate'
          return (
            <li key={`${item.name}-${index}`} className="upfile">
              <FileTypeBadge name={item.name} size="md" />
              <div className="upfile__main">
                <span className="upfile__name" title={item.name}>{item.name}</span>
                <span className="upfile__sub">
                  {size !== undefined && <span className="tnum">{formatFileSize(size)}</span>}
                  {item.document && <>{size !== undefined && ' · '}<Link to={`/kho/${item.document.id}`} onClick={onNavigate}>Mở văn bản <Icon name="arrowRight" size={14} /></Link></>}
                  {duplicate && item.existing_id ? <>{size !== undefined && ' · '}<Link to={`/kho/${item.existing_id}`} onClick={onNavigate}>Mở văn bản đã có <Icon name="arrowRight" size={14} /></Link></> : null}
                </span>
                {!item.document && item.error && <span className={duplicate ? 'upfile__reason upfile__reason--warn' : 'upfile__reason'}>{item.error}</span>}
              </div>
              {item.document ? (
                <Chip tone="green" icon="checkCircle" filled>Thành công</Chip>
              ) : duplicate ? (
                <Chip tone="amber" icon="copy">Trùng lặp</Chip>
              ) : (
                <Chip tone="red" icon="alertCircle" filled>Lỗi</Chip>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
