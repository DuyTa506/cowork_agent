import { useEffect, useRef, useState, type DragEvent } from 'react'
import { formatCheckApi } from '../../api'
import type { CheckOptions, CheckSession } from '../../api/formatCheck'
import { useAsyncData } from '../../hooks/useAsyncData'
import { formatFileSize } from '../../lib/format'
import { Button } from '../Button'
import { FileTypeBadge } from '../FileTypeBadge'
import { Icon } from '../Icon'
import { Select } from '../Select'
import { Spinner } from '../Spinner'
import { Switch } from '../Switch'
import { describeFailure, type FailureText } from './model'
import { FailureNotice, Notice } from './Notice'

const FALLBACK_ACCEPT = ['.docx', '.doc', '.pdf']

interface CheckUploadProps {
  onChecked: (session: CheckSession) => void
}

type Phase = 'idle' | 'uploading'

const normalizeExtension = (value: string) => (value.startsWith('.') ? value : `.${value}`).toLowerCase()

const STEPS = [
  { title: 'Chọn tệp', text: 'Tải lên tệp Word hoặc PDF cần kiểm tra.' },
  { title: 'Xem kết quả', text: 'Lỗi thể thức và chính tả, đối chiếu ngay trên văn bản.' },
  { title: 'Sửa và tải về', text: 'Chọn mục tự sửa, tải bản đã sửa hoặc báo cáo.' },
]

const TYPE_SAMPLES = [
  { name: 'mau.docx', caption: 'Word' },
  { name: 'mau.doc', caption: 'Word cũ' },
  { name: 'mau.pdf', caption: 'PDF' },
]

/** First screen: choose or drop one file (it is uploaded and checked straight away); options sit beside it. */
export function CheckUpload({ onChecked }: CheckUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const { data: options, error: optionsError, loading: optionsLoading, reload } = useAsyncData((signal) => formatCheckApi.getOptions(signal), [])
  const [profile, setProfile] = useState<string | null>(null)
  const [spell, setSpell] = useState<boolean | null>(null)
  const [dragging, setDragging] = useState(false)
  const [phase, setPhase] = useState<Phase>('idle')
  const [progress, setProgress] = useState(0)
  const [picked, setPicked] = useState<{ name: string; size: number } | null>(null)
  const [failure, setFailure] = useState<FailureText | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const accept = options?.accept.map(normalizeExtension) ?? FALLBACK_ACCEPT
  const chosenProfile = profile ?? options?.default_profile ?? ''
  const chosenSpell = spell ?? options?.default_spell ?? true
  const uploading = phase === 'uploading'
  const sentAll = uploading && progress >= 1
  const step = !uploading ? 0 : sentAll ? 1 : 0

  // Leaving the screen mid-upload must not update a component that is gone.
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])

  const start = async (incoming: FileList | File[]) => {
    const list = Array.from(incoming)
    const file = list[0]
    if (!file || uploading) return
    setNotice(list.length > 1 ? 'Mỗi lần chỉ kiểm tra một tệp: đã lấy tệp đầu tiên.' : null)
    const problem = validate(file, accept, options)
    if (problem) {
      setFailure(problem)
      return
    }
    setFailure(null)
    setPicked({ name: file.name, size: file.size })
    setProgress(0)
    setPhase('uploading')
    try {
      const session = await formatCheckApi.uploadFile(file, { profile: chosenProfile || undefined, spell: chosenSpell }, setProgress)
      if (mounted.current) onChecked(session)
      else formatCheckApi.discardCheck(session.id)
    } catch (error) {
      if (!mounted.current) return
      setFailure(describeFailure(error, 'Không kiểm tra được tệp'))
      setPhase('idle')
    }
  }

  const onDrop = (event: DragEvent) => {
    event.preventDefault()
    setDragging(false)
    void start(event.dataTransfer.files)
  }

  const choose = () => {
    if (!uploading) inputRef.current?.click()
  }

  const profileOptions = (options?.profiles ?? []).map((item) => ({ value: item.id, label: item.experimental ? `${item.label} (thử nghiệm)` : item.label }))
  const experimental = options?.profiles.find((item) => item.id === chosenProfile)?.experimental ?? false
  const acceptText = accept.join(' ')

  return (
    <div className="check check--upload">
      <header className="check-head">
        <h1 className="check-head__title">Kiểm tra thể thức và chính tả</h1>
        <p className="check-head__desc">Đối chiếu văn bản với thể thức quy định (Thông tư 68/2023/TT-BQP) và soát chính tả tiếng Việt.</p>
        <p className="check-info">
          <Icon name="shield" size={18} />
          <span>
            Tệp chỉ lưu tạm trong thư mục riêng của bạn, không lập chỉ mục, không vào kho văn bản
            {options ? `; tự xóa sau ${options.retention_hours} giờ` : ''}.
          </span>
        </p>
      </header>

      <div className="check-upload">
        <div className="check-upload__main">
          {failure && (
            <FailureNotice
              failure={failure}
              actions={failure.kind === 'network' ? undefined : <Button icon="upload" onClick={choose}>Chọn tệp khác</Button>}
            />
          )}
          {notice && <Notice tone="info" icon="info" title={notice} />}

          <div
            className={['check-drop', dragging && 'check-drop--over', uploading && 'check-drop--busy'].filter(Boolean).join(' ')}
            aria-busy={uploading}
            onClick={choose}
            onDragOver={(event) => { event.preventDefault(); if (!uploading) setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
          >
            {uploading && picked ? (
              <div className="check-drop__busy" aria-live="polite">
                <FileTypeBadge name={picked.name} size="lg" />
                <strong className="check-drop__file">{picked.name}</strong>
                <span className="check-drop__size">{formatFileSize(picked.size)}</span>
                <div
                  className={sentAll ? 'check-progress check-progress--busy' : 'check-progress'}
                  role="progressbar"
                  aria-label="Tiến độ kiểm tra"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={sentAll ? undefined : Math.round(progress * 100)}
                >
                  <div className="check-progress__fill" style={{ width: `${progress * 100}%` }} />
                </div>
                <p className="check-drop__status">
                  <Spinner />
                  {sentAll ? 'Đang kiểm tra thể thức và chính tả. Văn bản dài có thể mất vài chục giây.' : `Đang tải lên… ${Math.round(progress * 100)}%`}
                </p>
              </div>
            ) : (
              <>
                <div className="check-drop__types" aria-hidden="true">
                  {TYPE_SAMPLES.map((sample) => (
                    <span key={sample.name} className="check-drop__type">
                      <FileTypeBadge name={sample.name} size="lg" />
                      <span>{sample.caption}</span>
                    </span>
                  ))}
                </div>
                <h2 className="check-drop__title">Kéo thả hoặc chọn tệp</h2>
                <p className="check-drop__hint">
                  <span className="tnum">{acceptText}</span>
                  {options ? <> · tối đa <span className="tnum">{options.max_mb} MB</span></> : null}
                </p>
                <Button
                  variant="primary"
                  icon="upload"
                  className="check-drop__button"
                  onClick={(event) => { event.stopPropagation(); choose() }}
                >
                  Chọn tệp từ máy
                </Button>
                <p className="check-drop__note">Chỉ tệp Word mới sửa được trực tiếp; PDF chỉ được kiểm tra.</p>
              </>
            )}
            <input
              ref={inputRef}
              type="file"
              hidden
              accept={accept.join(',')}
              onClick={(event) => event.stopPropagation()}
              onChange={(event) => {
                if (event.target.files) void start(event.target.files)
                event.target.value = ''
              }}
            />
          </div>
        </div>

        <aside className="check-card check-options" aria-label="Tùy chọn kiểm tra" aria-busy={optionsLoading}>
          <h2 className="check-card__title">Tùy chọn kiểm tra</h2>
          {optionsLoading && !options ? (
            <Spinner label="Đang tải tùy chọn" />
          ) : (
            <>
              {optionsError && !options && (
                <Notice
                  tone="warning"
                  icon="alert"
                  title="Chưa tải được tùy chọn"
                  actions={<Button onClick={reload}>Thử lại</Button>}
                >
                  <p>{optionsError.message} Vẫn có thể kiểm tra với tùy chọn mặc định của hệ thống.</p>
                </Notice>
              )}
              {profileOptions.length > 0 && (
                <div className="check-field">
                  <label className="check-field__label" htmlFor="check-profile">Bộ luật thể thức</label>
                  <Select id="check-profile" value={chosenProfile} options={profileOptions} onChange={setProfile} disabled={uploading} />
                  <p className="check-field__help">
                    {experimental ? 'Bộ luật thử nghiệm: kết quả chỉ để tham khảo.' : 'Quy tắc dùng để đối chiếu thể thức văn bản.'}
                  </p>
                </div>
              )}
              <div className="check-field">
                <Switch checked={chosenSpell} onChange={setSpell} label="Soát chính tả tiếng Việt" disabled={uploading} />
                <p className="check-field__help">Từ nghi sai được gạch chân trong bản xem trước, kèm gợi ý sửa.</p>
              </div>
            </>
          )}
        </aside>

        <ol className="check-steps" aria-label="Các bước">
          {STEPS.map((item, index) => {
            const state = index < step ? 'done' : index === step ? 'current' : 'todo'
            return (
              <li key={item.title} className={`check-step check-step--${state}`} aria-current={state === 'current' ? 'step' : undefined}>
                <span className="check-step__num">{state === 'done' ? <Icon name="check" size={16} /> : index + 1}</span>
                <span className="check-step__text">
                  <strong>{item.title}</strong>
                  <span>{item.text}</span>
                </span>
                {index < STEPS.length - 1 && <Icon name="arrowRight" size={16} className="check-step__arrow" />}
              </li>
            )
          })}
        </ol>
      </div>
    </div>
  )
}

/** Quick checks before upload so obvious mistakes do not wait for a round trip. */
function validate(file: File, accept: string[], options: CheckOptions | null): FailureText | null {
  const lower = file.name.toLowerCase()
  if (!accept.some((extension) => lower.endsWith(extension))) {
    return { title: 'Định dạng tệp chưa được hỗ trợ', message: `“${file.name}” không phải tệp ${accept.join(', ')}.`, kind: 'unsupported' }
  }
  if (file.size === 0) return { title: 'Tệp rỗng', message: `“${file.name}” không có nội dung.`, kind: 'empty' }
  if (options && file.size > options.max_mb * 1024 * 1024) {
    return { title: 'Tệp quá lớn', message: `“${file.name}” (${formatFileSize(file.size)}) vượt quá giới hạn ${options.max_mb} MB.`, kind: 'too_large' }
  }
  return null
}
