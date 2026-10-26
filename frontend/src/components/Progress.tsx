interface ProgressProps {
  /** 0–100; omit for an indeterminate bar. */
  value?: number
  label?: string
  /** Text at the right of the label ("3/5 tệp"). */
  valueText?: string
  tone?: 'primary' | 'ok' | 'danger'
}

/** Thin progress bar for uploads and long jobs. */
export function Progress({ value, label, valueText, tone = 'primary' }: ProgressProps) {
  const determinate = value !== undefined
  return (
    <div className={['meter', `meter--${tone}`, !determinate && 'meter--indeterminate'].filter(Boolean).join(' ')}>
      {(label || valueText) && (
        <div className="meter__label"><span>{label}</span><span className="tnum">{valueText}</span></div>
      )}
      <div className="meter__bar" role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={determinate ? Math.round(value) : undefined}>
        <div className="meter__fill" style={determinate ? { width: `${Math.min(100, Math.max(0, value))}%` } : undefined} />
      </div>
    </div>
  )
}
