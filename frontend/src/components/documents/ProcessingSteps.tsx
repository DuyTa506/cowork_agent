import type { ProcessingStep } from '../../api'
import { formatDuration, stepDurations } from '../../lib/documents'
import { formatTime } from '../../lib/format'
import { Icon, type IconName } from '../Icon'

const STEP_STATE_TEXT: Record<ProcessingStep['state'], string> = {
  done: 'Hoàn tất',
  running: 'Đang chạy',
  failed: 'Lỗi',
  pending: 'Chờ',
}

const MARKER_ICONS: Record<ProcessingStep['state'], IconName> = {
  done: 'check',
  running: 'spinner',
  failed: 'close',
  pending: 'clock',
}

interface ProcessingStepsProps {
  steps: ProcessingStep[]
  /** When the file was received: shown as the first step. */
  uploadedAt?: string
  uploadedBy?: string
}

/** Vertical stepper of the processing pipeline: a state marker per step, its detail, finish time and how long it took. */
export function ProcessingSteps({ steps, uploadedAt, uploadedBy }: ProcessingStepsProps) {
  if (steps.length === 0 && !uploadedAt) return <p className="sub">Chưa bắt đầu xử lý.</p>
  const durations = stepDurations(steps)
  const finished = steps.length > 0 && steps.every((step) => step.state === 'done')
  const total = finished && steps.length > 1 ? durations.reduce<number>((sum, value) => sum + (value ?? 0), 0) : null

  return (
    <div className="stepper-wrap">
      <ol className="stepper">
        {uploadedAt && (
          <li className="stepper__item stepper__item--done">
            <span className="stepper__marker"><Icon name="upload" size={16} /></span>
            <div className="stepper__body">
              <div className="stepper__label">Tiếp nhận tệp<span className="sr-only"> ({STEP_STATE_TEXT.done})</span></div>
              {uploadedBy && <div className="stepper__detail">Bởi {uploadedBy}</div>}
            </div>
            <div className="stepper__meta"><time className="tnum">{formatTime(uploadedAt)}</time></div>
          </li>
        )}
        {steps.map((step, index) => {
          const time = step.state === 'done' || step.state === 'failed' ? formatTime(step.at) : ''
          const duration = durations[index]
          return (
            <li key={step.key} className={`stepper__item stepper__item--${step.state}`} aria-busy={step.state === 'running' || undefined}>
              <span className="stepper__marker">
                <Icon name={MARKER_ICONS[step.state]} size={16} className={step.state === 'running' ? 'stepper__spin' : undefined} />
              </span>
              <div className="stepper__body">
                <div className="stepper__label">
                  {step.label}
                  <span className="sr-only"> ({STEP_STATE_TEXT[step.state]})</span>
                </div>
                {step.detail && <div className="stepper__detail">{step.detail}</div>}
                {step.state === 'running' && !step.detail && <div className="stepper__detail">Đang chạy…</div>}
              </div>
              <div className="stepper__meta">
                {time && <time className="tnum">{time}</time>}
                {duration !== null && duration !== undefined && <span className="stepper__dur tnum">{formatDuration(duration)}</span>}
              </div>
            </li>
          )
        })}
      </ol>
      {total !== null && (
        <p className="stepper__total">
          <Icon name="clock" size={16} /> Tổng thời gian các bước <strong className="tnum">{formatDuration(total)}</strong>
        </p>
      )}
    </div>
  )
}
