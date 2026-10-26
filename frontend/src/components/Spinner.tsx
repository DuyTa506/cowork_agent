interface SpinnerProps {
  /** Accessible description; without it the spinner is purely decorative. */
  label?: string
  /** Pixels (default 16). */
  size?: number
  className?: string
}

/** Small rotating ring for work in progress. Size comes from a CSS variable so no inline style soup is needed in CSS. */
export function Spinner({ label, size = 16, className }: SpinnerProps) {
  return (
    <span
      className={['spinner', className].filter(Boolean).join(' ')}
      style={size === 16 ? undefined : { width: size, height: size, borderWidth: size >= 28 ? 3 : 2 }}
      role={label ? 'status' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    />
  )
}
