import { useEffect, useRef, useState } from 'react'
import type { CheckFile, FixMode } from '../../api/formatCheck'
import { Button } from '../Button'
import { Select } from '../Select'
import { Menu, type MenuItem } from './Menu'

const MODE_OPTIONS = [
  { value: 'track', label: 'Track Changes (ghi dấu)' },
  { value: 'apply', label: 'Sửa trực tiếp' },
]

export const DOWNLOADS: { file: CheckFile; short: string; label: string; wordOnly: boolean }[] = [
  { file: 'fixed', short: 'Bản đã sửa', label: 'Tải bản đã sửa (.docx)', wordOnly: true },
  { file: 'annotated', short: 'Bản có ghi chú', label: 'Tải bản có ghi chú (.docx)', wordOnly: true },
  { file: 'report', short: 'Báo cáo', label: 'Tải báo cáo lỗi', wordOnly: false },
]

interface ActionBarProps {
  canFix: boolean
  /** A corrected copy exists. */
  fixed: boolean
  busy: null | 'fix' | 'recheck' | CheckFile
  chosen: number
  /** Nothing new to apply: same selection and mode as the corrected copy. */
  unchanged: boolean
  expired: boolean
  mode: FixMode
  onMode: (mode: FixMode) => void
  onFix: () => void
  onDownload: (file: CheckFile) => void
  onSave: () => void
  onReset: () => void
}

const FIXED_HINT = 'Chọn mục cần sửa rồi bấm “Sửa” để có bản đã sửa'

/** Stays at the bottom edge of the window: fix, download, save to the store, pick another file. */
export function ActionBar({ canFix, fixed, busy, chosen, unchanged, expired, mode, onMode, onFix, onDownload, onSave, onReset }: ActionBarProps) {
  // The bar sits in the page area, whose width depends on the sidebar: lay it out by its own width, not the window's.
  const barRef = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(1400)
  useEffect(() => {
    const element = barRef.current
    if (!element) return
    setWidth(element.clientWidth)
    const observer = new ResizeObserver(() => setWidth(element.clientWidth))
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  const narrow = width < 760
  const compact = width < 1300
  const idle = busy === null
  const downloads = DOWNLOADS.filter((entry) => !entry.wordOnly || canFix)

  const menuItems: MenuItem[] = [
    ...downloads.map((entry) => ({
      key: entry.file,
      label: entry.label,
      icon: 'download' as const,
      disabled: !idle || (entry.file === 'fixed' && !fixed),
      description: entry.file === 'fixed' && !fixed ? FIXED_HINT : undefined,
      onSelect: () => onDownload(entry.file),
    })),
    { key: 'save', label: 'Lưu vào kho văn bản', icon: 'folder' as const, disabled: !idle, separatorBefore: true, onSelect: onSave },
    { key: 'reset', label: 'Chọn tệp khác', icon: 'upload' as const, disabled: !idle, onSelect: onReset },
  ]

  return (
    <div className="check-bar" ref={barRef} role="region" aria-label="Thao tác với kết quả">
      <div className="check-bar__inner">
        {canFix && (
          <div className="check-bar__fix">
            <Select aria-label="Cách sửa" value={mode} options={MODE_OPTIONS} onChange={(value) => onMode(value as FixMode)} disabled={!idle} className="check-bar__mode" />
            <Button variant="primary" icon="check" className="check-bar__primary" loading={busy === 'fix'} disabled={!idle || chosen === 0 || unchanged || expired} onClick={onFix}>
              {`Sửa ${chosen} mục đã chọn`}
            </Button>
          </div>
        )}
        {narrow ? (
          <Menu label="Tải về và lưu" ariaLabel="Tải về, lưu vào kho, chọn tệp khác" icon="download" items={menuItems} align="end" direction="up" className="check-bar__more" />
        ) : (
          <>
            {compact ? (
              <Menu
                label="Tải về"
                ariaLabel="Tải về"
                icon="download"
                items={menuItems.filter((entry) => downloads.some((download) => download.file === entry.key))}
                direction="up"
                className="check-bar__dl"
              />
            ) : (
            <div className="check-bar__downloads" role="group" aria-label="Tải về">
              <span className="check-bar__caption">Tải về</span>
              {downloads.map((entry) => (
                <Button
                  key={entry.file}
                  icon="download"
                  aria-label={entry.label}
                  loading={busy === entry.file}
                  disabled={!idle || (entry.file === 'fixed' && !fixed)}
                  title={entry.file === 'fixed' && !fixed ? FIXED_HINT : entry.label}
                  onClick={() => onDownload(entry.file)}
                >
                  {entry.short}
                </Button>
              ))}
            </div>
            )}
            <span className="spacer" />
            <Button icon="folder" onClick={onSave} disabled={!idle}>Lưu vào kho văn bản</Button>
            <Button variant="ghost" onClick={onReset} disabled={!idle}>Chọn tệp khác</Button>
          </>
        )}
      </div>
    </div>
  )
}
