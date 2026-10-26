import type { ReactNode } from 'react'
import type { DocumentLevel, DocumentState } from '../api'
import { LEVEL_LABELS, STATE_LABELS } from '../lib/labels'
import type { Tone } from '../lib/labels'
import { Icon } from './Icon'
import type { IconName } from './Icon'

/** Semantic names, plus the older colour names (`green`, `blue`, `amber`, `red`, `grey`) that still work. */
export type ChipTone = 'ok' | 'info' | 'warn' | 'danger' | 'neutral' | 'brand' | Tone

interface ChipProps {
  tone?: ChipTone
  icon?: IconName
  /** Leading dot instead of an icon (quiet status). */
  dot?: boolean
  /** Filled (high emphasis) instead of tinted. */
  solid?: boolean
  /** Spins the icon, or pulses the dot (work in progress). */
  busy?: boolean
  size?: 'md' | 'lg'
  /** Ignored: kept for call sites written before the redesign. */
  filled?: boolean
  children: ReactNode
}

/** Pill label with a dot or icon and text: status is never conveyed by colour alone. 22 px high (`lg`: 28 px). */
export function Chip({ tone = 'neutral', icon, dot, solid, busy, size = 'md', children }: ChipProps) {
  const classes = ['pill', `pill--${tone}`, solid && 'pill--solid', size === 'lg' && 'pill--lg', icon && 'pill--icon'].filter(Boolean).join(' ')
  return (
    <span className={classes}>
      {icon ? <Icon name={icon} size={size === 'lg' ? 16 : 14} className={busy ? 'pill__spin' : undefined} /> : dot ? <i className={`pill__dot${busy ? ' pill__dot--pulse' : ''}`} aria-hidden="true" /> : null}
      {children}
    </span>
  )
}

interface BadgeProps {
  tone?: ChipTone
  icon?: IconName
  children: ReactNode
}

/** Small count or role label (no border, 20 px): "Quản trị viên", "12". Use Chip for statuses. */
export function Badge({ tone = 'neutral', icon, children }: BadgeProps) {
  return (
    <span className={`badge badge--${tone}`}>
      {icon && <Icon name={icon} size={14} />}
      {children}
    </span>
  )
}

const STATE_TONES: Record<DocumentState, ChipTone> = {
  uploaded: 'neutral',
  processing: 'info',
  ready: 'ok',
  needs_review: 'warn',
  needs_ocr: 'warn',
  failed: 'danger',
}

/** Processing state of a document: Chờ xử lý, Đang xử lý (animated dot), Sẵn sàng, Cần rà soát, Cần OCR, Lỗi. */
export function StateChip({ state, size }: { state: DocumentState; size?: 'md' | 'lg' }) {
  return (
    <span aria-busy={state === 'processing' || undefined}>
      <Chip tone={STATE_TONES[state]} dot busy={state === 'processing'} size={size}>{STATE_LABELS[state]}</Chip>
    </span>
  )
}

/** Secrecy level: "Mật" is a solid red chip with a shield, "Thường" a quiet neutral one. */
export function LevelChip({ level, size }: { level: DocumentLevel; size?: 'md' | 'lg' }) {
  return level === 'mat' ? (
    <Chip tone="danger" icon="shieldAlert" solid size={size}>{LEVEL_LABELS.mat}</Chip>
  ) : (
    <Chip tone="neutral" size={size}>{LEVEL_LABELS.thuong}</Chip>
  )
}
