import { useEffect, useRef, useState, type KeyboardEvent } from 'react'

interface InlineEditorProps {
  value: string
  label: string
  /** Enter adds a line (Ctrl+Enter saves) instead of saving. */
  multiline?: boolean
  className?: string
  onCommit: (value: string) => void
  onCancel: () => void
}

/** Text box that replaces a piece of the page while it is edited: Enter or leaving it saves, Esc cancels. */
export function InlineEditor({ value, label, multiline = false, className, onCommit, onCancel }: InlineEditorProps) {
  const ref = useRef<HTMLTextAreaElement>(null)
  const [text, setText] = useState(value)
  const finished = useRef(false)

  const fit = () => {
    const area = ref.current
    if (!area) return
    area.style.height = 'auto'
    area.style.height = `${area.scrollHeight}px`
  }

  useEffect(() => {
    const area = ref.current
    if (!area) return
    area.focus()
    area.setSelectionRange(area.value.length, area.value.length)
    fit()
  }, [])

  const commit = () => {
    if (finished.current) return
    finished.current = true
    if (text === value) onCancel()
    else onCommit(text)
  }

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      finished.current = true
      onCancel()
      return
    }
    if (event.key !== 'Enter' || event.nativeEvent.isComposing) return
    if (multiline ? event.ctrlKey || event.metaKey : !event.shiftKey) {
      event.preventDefault()
      commit()
    }
  }

  return (
    <textarea
      ref={ref}
      className={['cv-editor', className].filter(Boolean).join(' ')}
      aria-label={label}
      rows={1}
      value={text}
      onChange={(event) => {
        setText(event.target.value)
        fit()
      }}
      onKeyDown={onKeyDown}
      onBlur={commit}
    />
  )
}
