import { useEffect, useState, type RefObject } from 'react'

export type AskAction = 'rewrite' | 'shorten' | 'military' | 'spelling'

export const ASK_LABELS: Record<AskAction, string> = {
  rewrite: 'Viết lại',
  shorten: 'Rút gọn',
  military: 'Văn phong quân sự',
  spelling: 'Chính tả',
}

/** The request sent to the assistant for each action; the selected text travels separately as `context`. */
export const ASK_PROMPTS: Record<AskAction, string> = {
  rewrite: 'Viết lại đoạn đã chọn cho rõ ràng, mạch lạc hơn, giữ nguyên ý.',
  shorten: 'Rút gọn đoạn đã chọn, giữ đủ ý chính.',
  military: 'Chuyển đoạn đã chọn sang văn phong quân đội theo cách viết của đơn vị tôi, đúng thể thức văn bản hành chính.',
  spelling: 'Kiểm tra và sửa lỗi chính tả, ngữ pháp trong đoạn đã chọn.',
}

export interface SelectionInfo {
  blockId: string
  text: string
  x: number
  /** Top of the selection; the toolbar sits above it (or below when there is no room). */
  top: number
  bottom: number
}

/**
 * Follows the text selection inside `rootRef`: when it lies within one block (`[data-block-id]`) it reports the block,
 * the selected text and where to put the toolbar. Scrolling hides it because it is positioned on the screen.
 */
export function useBlockSelection(rootRef: RefObject<HTMLElement | null>, scrollRef: RefObject<HTMLElement | null>): [SelectionInfo | null, () => void] {
  const [info, setInfo] = useState<SelectionInfo | null>(null)

  useEffect(() => {
    const root = rootRef.current
    if (!root) return
    const blockOf = (node: Node | null): HTMLElement | null => (node instanceof Element ? node : node?.parentElement ?? null)?.closest<HTMLElement>('[data-block-id]') ?? null

    const read = () => {
      const selection = window.getSelection()
      if (!selection || selection.isCollapsed || selection.rangeCount === 0) return setInfo(null)
      const range = selection.getRangeAt(0)
      const start = blockOf(range.startContainer)
      const end = blockOf(range.endContainer)
      const text = selection.toString().trim()
      if (!start || start !== end || !root.contains(start) || !text || start.dataset.blockId === undefined) return setInfo(null)
      const rect = range.getBoundingClientRect()
      setInfo({ blockId: start.dataset.blockId, text, x: rect.left + rect.width / 2, top: rect.top, bottom: rect.bottom })
    }

    // The selection settles after the pointer or key is released.
    root.addEventListener('mouseup', read)
    root.addEventListener('keyup', read)
    const hide = () => setInfo(null)
    const scroller = scrollRef.current
    scroller?.addEventListener('scroll', hide, { passive: true })
    window.addEventListener('resize', hide)
    // Pressing anywhere outside the sheet and the toolbar (another tab, a button) drops the toolbar.
    const onOutside = (event: PointerEvent) => {
      const target = event.target as Element | null
      if (!root.contains(target) && !target?.closest('.cv-seltool')) setInfo(null)
    }
    document.addEventListener('pointerdown', onOutside, true)
    return () => {
      document.removeEventListener('pointerdown', onOutside, true)
      root.removeEventListener('mouseup', read)
      root.removeEventListener('keyup', read)
      scroller?.removeEventListener('scroll', hide)
      window.removeEventListener('resize', hide)
    }
  }, [rootRef, scrollRef])

  return [info, () => setInfo(null)]
}

interface SelectionToolbarProps {
  info: SelectionInfo
  disabled: boolean
  onAsk: (action: AskAction) => void
}

/** Floating buttons over a selected passage: rewrite, shorten, military style, spelling. */
export function SelectionToolbar({ info, disabled, onAsk }: SelectionToolbarProps) {
  const below = info.top < 64
  return (
    <div
      className="cv-seltool"
      role="toolbar"
      aria-label="Nhờ trợ lý chỉnh đoạn đã chọn"
      style={{ left: info.x, top: below ? info.bottom + 8 : info.top - 8, transform: below ? 'translateX(-50%)' : 'translate(-50%, -100%)' }}
      // Keep the selection while a button is pressed.
      onMouseDown={(event) => event.preventDefault()}
    >
      {(Object.keys(ASK_LABELS) as AskAction[]).map((action) => (
        <button key={action} type="button" className="cv-seltool__btn" disabled={disabled} onClick={() => onAsk(action)}>
          {ASK_LABELS[action]}
        </button>
      ))}
    </div>
  )
}
