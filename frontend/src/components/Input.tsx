import { useState, type InputHTMLAttributes, type ReactNode, type TextareaHTMLAttributes } from 'react'
import { Icon, type IconName } from './Icon'
import { IconButton } from './IconButton'

export interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'size'> {
  /** 28 px `sm`, 36 px `md` (default), 44 px `lg`. */
  size?: 'sm' | 'md' | 'lg'
  /** Leading icon inside the box (search, user, lock). */
  icon?: IconName
  /** Trailing slot inside the box (a clear button, a unit). */
  end?: ReactNode
  /** Red border; also set automatically from `aria-invalid`. */
  invalid?: boolean
  /** For `type="password"`: adds a show / hide button. */
  revealable?: boolean
}

/** Text input. Wrap it in `<Field>` for the label, hint and error. Always give it a label or an `aria-label`. */
export function Input({ size = 'md', icon, end, invalid, revealable, type = 'text', className, ...rest }: InputProps) {
  const [shown, setShown] = useState(false)
  const reveal = revealable && type === 'password'
  const control = (
    <input
      type={reveal && shown ? 'text' : type}
      className={['input', size !== 'md' && `input--${size}`, className].filter(Boolean).join(' ')}
      aria-invalid={invalid || rest['aria-invalid'] || undefined}
      {...rest}
    />
  )
  if (!icon && !end && !reveal) return control
  return (
    <span className={['input-wrap', (end || reveal) && 'input-wrap--end'].filter(Boolean).join(' ')}>
      {icon && <Icon name={icon} size={size === 'lg' ? 20 : 18} />}
      {control}
      {(end || reveal) && (
        <span className="input-wrap__end">
          {end}
          {reveal && (
            <IconButton
              icon={shown ? 'eyeOff' : 'eye'}
              label={shown ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
              size="sm"
              aria-pressed={shown}
              onClick={() => setShown((value) => !value)}
            />
          )}
        </span>
      )}
    </span>
  )
}

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  invalid?: boolean
}

/** Multi-line input; grows by dragging the corner. */
export function Textarea({ invalid, className, ...rest }: TextareaProps) {
  return <textarea className={['textarea', className].filter(Boolean).join(' ')} aria-invalid={invalid || rest['aria-invalid'] || undefined} {...rest} />
}
