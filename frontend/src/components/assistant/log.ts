import type { ChatStep } from '../../api/chat'
import type { UiMessage } from './types'

/** "2,1 giây", "48 giây", "1 phút 05 giây": how long a turn took. */
export function formatSeconds(ms: number): string {
  const seconds = Math.max(0, ms) / 1000
  if (seconds < 10) return `${seconds.toFixed(1).replace('.', ',')} giây`
  if (seconds < 60) return `${Math.round(seconds)} giây`
  const minutes = Math.floor(seconds / 60)
  return `${minutes} phút ${String(Math.round(seconds - minutes * 60)).padStart(2, '0')} giây`
}

/** Short duration of one step: "0,1 giây". */
export function stepDuration(step: ChatStep): string {
  if (step.status === 'running') return ''
  return step.duration_ms < 50 ? '< 0,1 giây' : formatSeconds(step.duration_ms)
}

/** Time the assistant needed for a stored answer: the gap between the question and the answer; falls back to the steps' own durations. */
export function turnDuration(message: UiMessage, question: UiMessage | undefined): number {
  if (message.durationMs !== undefined) return message.durationMs
  const stamp = (value: string) => new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(value) ? value : `${value}Z`).getTime()
  if (question) {
    const gap = stamp(message.created_at) - stamp(question.created_at)
    if (Number.isFinite(gap) && gap >= 0 && gap < 3_600_000) return gap
  }
  return message.steps.reduce((sum, step) => sum + step.duration_ms, 0)
}

/** Groups used by the conversation list. */
export type DayGroup = 'today' | 'week' | 'older'

export const GROUP_LABELS: Record<DayGroup, string> = { today: 'Hôm nay', week: 'Tuần này', older: 'Cũ hơn' }

export function dayGroup(updatedAt: string, now = new Date()): DayGroup {
  const date = new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(updatedAt) ? updatedAt : `${updatedAt}Z`)
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  if (date.getTime() >= startOfToday) return 'today'
  // "This week" = the last 7 days including today.
  if (date.getTime() >= startOfToday - 6 * 86_400_000) return 'week'
  return 'older'
}

/** Names of the steps being worked on right now: "Tìm văn bản" or "Tìm văn bản (2 việc song song)". */
export function runningLabel(steps: ChatStep[]): string {
  const active = steps.filter((step) => step.status === 'running')
  if (active.length === 0) return ''
  const names = [...new Set(active.map((step) => step.title))]
  return active.length > 1 ? `${names.join(', ')} · ${active.length} việc song song` : (names[0] ?? '')
}

const two = (value: number): string => String(value).padStart(2, '0')

/** "14:32" for a conversation updated today, "24/10" for an older one. */
export function shortWhen(updatedAt: string): string {
  const date = new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(updatedAt) ? updatedAt : `${updatedAt}Z`)
  if (Number.isNaN(date.getTime())) return ''
  return dayGroup(updatedAt) === 'today' ? `${two(date.getHours())}:${two(date.getMinutes())}` : `${two(date.getDate())}/${two(date.getMonth() + 1)}`
}
