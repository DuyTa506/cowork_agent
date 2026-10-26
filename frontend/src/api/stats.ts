import { request } from './client'

export interface CountItem {
  key: string
  label: string
  count: number
}

export interface UnitCount {
  unit_id: string
  name: string
  branch_id: string
  branch: string
  count: number
}

export interface DayCount {
  /** yyyy-mm-dd, Vietnam time. */
  day: string
  count: number
}

export interface UnitUsage {
  unit_id: string
  name: string
  branch_id: string
  branch: string
  users: number
  active_users: number
  questions: number
  uploads: number
  moderation: number
  /** Questions per day over the period. */
  series: number[]
}

export interface ModerationEvent {
  at: string
  username: string
  unit_name: string
  action: 'block' | 'warn' | 'log'
}

export interface StatsTotals {
  documents: number
  ready: number
  needs_review: number
  needs_ocr: number
  failed: number
  processing: number
  secret: number
  scanned: number
  chunks: number
  users: number
  active_users: number
  questions_period: number
  questions_month: number
  uploads_period: number
  moderation_period: number
}

export interface CanvasUsage {
  proposals: number
  accepted: number
  rejected: number
  edited_after: number
}

export interface Stats {
  generated_at: string
  days: number
  scope: { unit_id: string; unit_name: string; everything: boolean }
  totals: StatsTotals
  by_state: CountItem[]
  by_type: CountItem[]
  by_level: CountItem[]
  by_tag: CountItem[]
  by_issued_year: CountItem[]
  by_unit: UnitCount[]
  uploads_by_month: CountItem[]
  questions_by_day: DayCount[]
  usage_by_unit: UnitUsage[]
  moderation_by_action: CountItem[]
  moderation_recent: ModerationEvent[]
  canvas: CanvasUsage
}

export const STATS_PERIODS = [7, 30, 90] as const

/** GET /api/stats?days= (administrators and commanders; a commander gets their unit's subtree). */
export function getStats(days: number, signal?: AbortSignal): Promise<Stats> {
  return request<Stats>('/api/stats', { query: { days }, signal })
}
