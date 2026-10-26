import { ApiError } from '../../api'
import type { CheckItem, CheckManual, CheckPara, CheckResult, Severity, Tier } from '../../api/formatCheck'
import type { IconName } from '../Icon'

/** How serious a finding is: the three severities of the format check plus spelling. */
export type Level = 'error' | 'warning' | 'info' | 'spelling'
export type FormatLevel = Exclude<Level, 'spelling'>

export const LEVEL_ORDER: Level[] = ['error', 'warning', 'spelling', 'info']

export type LevelTone = 'danger' | 'warning' | 'info' | 'neutral'

/** `short` is the filter button, `plural` the group title in the list, `label` the lower-case word inside a sentence. */
export const LEVELS: Record<Level, { label: string; short: string; plural: string; tone: LevelTone; icon: IconName }> = {
  error: { label: 'bắt buộc', short: 'Bắt buộc', plural: 'Bắt buộc sửa', tone: 'danger', icon: 'warnOctagon' },
  warning: { label: 'cảnh báo', short: 'Cảnh báo', plural: 'Cảnh báo', tone: 'warning', icon: 'alert' },
  spelling: { label: 'chính tả', short: 'Chính tả', plural: 'Chính tả', tone: 'info', icon: 'spellcheck' },
  info: { label: 'lưu ý', short: 'Lưu ý', plural: 'Lưu ý', tone: 'neutral', icon: 'info' },
}

/** One row of the findings list. A row with `items` can be ticked for automatic fixing (one item per place in the text). */
export interface Finding {
  key: string
  level: Level
  category: 'format' | 'spelling'
  message: string
  /** Where in the document, in words. */
  where: string
  /** Spelling: the text around the wrong word. */
  context?: { before: string; found: string; after: string }
  /** The fix, or what the user has to do. */
  hint: string
  /** Secondary line: legal basis, reason it cannot be fixed automatically. */
  note: string
  pis: number[]
  /** What the document has now and what it should be (empty when not known). */
  current: string
  target: string
  /** Legal basis ("Phụ lục I, ...") and the reason a hand fix is needed. */
  basis: string
  reason: string
  /** Confidence of the automatic fix; null for hand fixes. */
  confidence: Tier | null
  /** Fixes behind this row: the same change in several paragraphs is one row (doccheck's `group`). Empty when it needs hand work. */
  items: CheckItem[]
  /** Sort position inside the document: paragraph index times 100000 plus the offset in it. */
  pos: number
  /** Spelling: what kind of mistake ("Âm tiết sai", "Dấu câu"...); empty for format findings. */
  kindLabel: string
}

const LEVEL_RANK: Record<Level, number> = { error: 0, warning: 1, spelling: 2, info: 3 }

function formatLevel(severity: Severity | string): FormatLevel {
  return severity === 'error' ? 'error' : severity === 'info' ? 'info' : 'warning'
}

function truncate(text: string, length: number): string {
  return text.length > length ? `${text.slice(0, length - 1)}…` : text
}

/** "Trang 2 · Bảng · “Nâng cao trình độ…”" for a paragraph. */
export function placeOf(para: CheckPara | undefined): string {
  if (!para) return ''
  const bits: string[] = []
  const page = para.page ?? para.pg
  if (page) bits.push(`Trang ${page}`)
  if (para.where === 'cell') bits.push('Bảng')
  else if (para.where === 'textbox') bits.push('Hộp văn bản')
  const text = para.text.replace(/\s+/g, ' ').trim()
  bits.push(text ? `“${truncate(text, 48)}”` : 'Dòng trống')
  return bits.join(' · ')
}

function placesOf(pis: number[], paras: Map<number, CheckPara>): string {
  const first = pis[0]
  if (first === undefined) return 'Toàn văn bản'
  const place = placeOf(paras.get(first)) || `Đoạn ${first + 1}`
  return pis.length > 1 ? `${place} và ${pis.length - 1} đoạn khác` : place
}

function isSpellingManual(manual: CheckManual): boolean {
  return manual.id.startsWith('M:spl:') || manual.rule.startsWith('SPELL')
}

/** "Sửa cỡ chữ: 13 → 14" */
function fixText(item: CheckItem): string {
  if (item.details && item.details.length > 0) return item.details.join('; ')
  const label = item.label.toLocaleLowerCase('vi-VN')
  if (item.before && item.after) return `Sửa ${label}: ${item.before} → ${item.after}`
  if (item.after) return `Đặt ${label}: ${item.after}`
  return `Sửa ${label}`
}

/**
 * Turns the payload into the rows of the list, the way doccheck's own screen does: the same fix in several paragraphs is
 * one row, a note that `banner` and `manual` both carry is listed once, and spelling is one row per word. A paragraph message
 * that no row covers gets a row too (so nothing the server found is hidden). Sorted by severity, then position.
 */
export function buildFindings(result: Pick<CheckResult, 'paras' | 'manual' | 'banner' | 'items'>): Finding[] {
  const paras = new Map(result.paras.map((para) => [para.pi, para]))
  // Fixable items carry no severity of their own; borrow it from a hand-fix or banner finding of the same rule.
  const ruleLevel = new Map<string, FormatLevel>()
  const note = (rule: string, severity: Severity | string) => {
    const level = formatLevel(severity)
    const known = ruleLevel.get(rule)
    if (!known || LEVEL_RANK[level] < LEVEL_RANK[known]) ruleLevel.set(rule, level)
  }
  result.manual.filter((manual) => !isSpellingManual(manual)).forEach((manual) => note(manual.rule, manual.severity))
  result.banner.forEach((banner) => note(banner.rule, banner.severity))

  const rows: Finding[] = []
  const covered = new Set<number>()
  const seen = new Map<string, Finding>()

  // Hand-fix notes first (they carry the reason), then banner lines nothing else said; the same message is one row.
  const handRow = (key: string, level: FormatLevel, message: string, pis: number[], hint: string, reason: string, current = '', target = '') => {
    const known = seen.get(message)
    if (known) {
      for (const pi of pis) if (!known.pis.includes(pi)) known.pis.push(pi)
      known.where = placesOf(known.pis, paras)
      if (!known.hint) known.hint = hint
      if (LEVEL_RANK[level] < LEVEL_RANK[known.level]) known.level = level
      return
    }
    const row: Finding = {
      key,
      level,
      category: 'format',
      message,
      where: placesOf(pis, paras),
      hint,
      note: reason ? `Cần sửa tay · ${reason}` : 'Cần sửa tay',
      current,
      target,
      basis: '',
      reason,
      confidence: null,
      pis: [...pis],
      items: [],
      pos: (pis[0] ?? -1) * 100000,
      kindLabel: '',
    }
    seen.set(message, row)
    rows.push(row)
  }

  const banners = new Map(result.banner.map((banner) => [banner.message, banner]))
  for (const manual of result.manual) {
    manual.pis.forEach((pi) => { if (!isSpellingManual(manual)) covered.add(pi) })
    if (isSpellingManual(manual)) {
      const first = manual.pis[0]
      rows.push({
        key: `manual:${manual.id}`,
        level: 'spelling',
        category: 'spelling',
        message: manual.found ? `“${manual.found}” có thể sai chính tả.` : manual.message,
        where: placesOf(manual.pis, paras),
        context: manual.found && manual.ctx ? { before: manual.ctx[0], found: manual.found, after: manual.ctx[1] } : undefined,
        hint: manual.suggestion ? `Gợi ý: ${manual.suggestion}` : '',
        note: manual.reason,
        current: manual.found,
        target: manual.suggestion,
        basis: '',
        reason: manual.reason,
        confidence: null,
        pis: manual.pis,
        items: [],
        pos: (first ?? -1) * 100000,
        kindLabel: manual.label || 'Cần tự xem lại',
      })
      continue
    }
    const actual = banners.get(manual.message)?.actual
    const hint = manual.suggestion ? `Gợi ý: ${manual.suggestion}` : actual ? `Hiện có: ${actual}` : ''
    handRow(`manual:${manual.id}`, formatLevel(manual.severity), manual.message, manual.pis, hint, manual.reason, actual ?? manual.found, manual.suggestion)
  }

  // A banner line an automatic fix already covers (margins) is that fix's row, not a note.
  const fixedProps = new Set(result.items.map((item) => item.prop))
  result.banner.forEach((banner, index) => {
    if (fixedProps.has(banner.rule.split('.').pop() ?? '')) return
    handRow(`banner:${index}`, formatLevel(banner.severity), banner.message, [], banner.actual ? `Hiện có: ${banner.actual}` : '', '', banner.actual)
  })

  const groups = new Map<string, CheckItem[]>()
  for (const item of result.items) {
    const spelling = item.kind === 'spelling'
    if (item.pi !== null && !spelling) covered.add(item.pi)
    const key = spelling ? `item:${item.id}` : `group:${item.tier}|${item.group}`
    groups.set(key, [...(groups.get(key) ?? []), item])
  }
  for (const [key, group] of groups) {
    const item = group[0]
    if (!item) continue
    const spelling = item.kind === 'spelling'
    const pis = group.flatMap((entry) => (entry.pi === null ? [] : [entry.pi]))
    const levels = group.flatMap((entry) => entry.rules.map((rule) => ruleLevel.get(rule))).filter((level): level is FormatLevel => level !== undefined)
    const level: Level = spelling ? 'spelling' : levels.sort((a, b) => LEVEL_RANK[a] - LEVEL_RANK[b])[0] ?? 'warning'
    const ctx = item.ctx
    // A stray or missing space: the word itself is blank, so say what is wrong and show the space as a visible mark.
    const blank = spelling && (item.found ?? '').trim() !== (item.found ?? '')
    const shown = blank ? item.before : item.found ?? item.before
    const where = pis.length === 0 ? 'Toàn văn bản' : pis.length > 1 ? `${pis.length} đoạn, đầu tiên: ${placeOf(paras.get(pis[0] ?? -1)) || `đoạn ${(pis[0] ?? 0) + 1}`}` : placeOf(paras.get(pis[0] ?? -1)) || `Đoạn ${(pis[0] ?? 0) + 1}`
    rows.push({
      key,
      level,
      category: spelling ? 'spelling' : 'format',
      message: spelling ? (blank ? item.explain || item.label : `“${shown}” có thể sai chính tả.`) : item.explain || item.label,
      where,
      context: spelling && ctx ? { before: ctx[0], found: shown, after: ctx[1] } : undefined,
      hint: spelling ? (blank ? `Sửa: ${item.before} → ${item.after || 'xóa'}` : `Gợi ý: ${item.raw_after === undefined || item.raw_after === '' ? 'xóa' : item.raw_after}`) : fixText(item),
      note: spelling ? [item.label, item.explain].filter(Boolean).join(' · ') : item.basis ? `Căn cứ: ${item.basis}` : '',
      current: spelling ? shown : item.before,
      target: spelling ? (blank ? item.after : item.raw_after ?? '') : item.after,
      basis: item.basis,
      reason: spelling ? item.explain : '',
      confidence: item.tier,
      pis,
      items: group,
      pos: (pis[0] ?? -1) * 100000 + (item.start ?? 0),
      kindLabel: spelling ? item.label : '',
    })
  }

  for (const para of result.paras) {
    if (covered.has(para.pi)) continue
    para.msgs.forEach((message, index) => {
      handRow(`msg:${para.pi}:${index}`, 'warning', message, [para.pi], '', '')
    })
  }

  return rows.sort((a, b) => LEVEL_RANK[a.level] - LEVEL_RANK[b.level] || a.pos - b.pos)
}

/** Worst format severity of each paragraph, for the underline colour in the preview. */
export function paragraphLevels(findings: Finding[]): Map<number, FormatLevel> {
  const levels = new Map<number, FormatLevel>()
  for (const finding of findings) {
    if (finding.level === 'spelling') continue
    for (const pi of finding.pis) {
      const known = levels.get(pi)
      if (!known || LEVEL_RANK[finding.level] < LEVEL_RANK[known]) levels.set(pi, finding.level as FormatLevel)
    }
  }
  return levels
}

export function countByLevel(findings: Finding[]): Record<Level, number> {
  const counts: Record<Level, number> = { error: 0, warning: 0, info: 0, spelling: 0 }
  for (const finding of findings) counts[finding.level] += 1
  return counts
}

/* ---------- selection of fixes ---------- */

export type ItemMap = Map<string, CheckItem>

export function itemMap(items: CheckItem[]): ItemMap {
  return new Map(items.map((item) => [item.id, item]))
}

/** Adds locked items and everything the chosen items require. */
function close(selected: Set<string>, byId: ItemMap): Set<string> {
  const result = new Set(selected)
  for (const item of byId.values()) if (item.locked) result.add(item.id)
  const pending = [...result]
  while (pending.length > 0) {
    const required = byId.get(pending.pop() ?? '')?.requires
    if (required && byId.has(required) && !result.has(required)) {
      result.add(required)
      pending.push(required)
    }
  }
  return result
}

/** Ticked by default: high and medium confidence (and the locked ones). */
export function defaultSelection(items: CheckItem[]): Set<string> {
  return close(new Set(items.filter((item) => item.tier !== 'thap').map((item) => item.id)), itemMap(items))
}

/** Ticks or unticks items (the places of one row), together with the items they need or that need them. */
export function toggleItems(selected: Set<string>, ids: string[], on: boolean, byId: ItemMap): Set<string> {
  const next = new Set(selected)
  if (on) {
    ids.forEach((id) => next.add(id))
    return close(next, byId)
  }
  ids.forEach((id) => next.delete(id))
  for (let changed = true; changed; ) {
    changed = false
    for (const item of byId.values()) {
      if (!item.locked && next.has(item.id) && item.requires && !next.has(item.requires)) {
        next.delete(item.id)
        changed = true
      }
    }
  }
  return close(next, byId)
}

export type QuickPick = 'all' | 'default' | 'error' | 'warning' | 'spelling' | 'none'

/** Fixable rows a quick pick would tick (without the dependencies it pulls in). */
export function pickMatches(pick: QuickPick, findings: Finding[]): Finding[] {
  const fixable = findings.filter((finding) => finding.items.length > 0)
  switch (pick) {
    case 'all': return fixable
    case 'default': return fixable.filter((finding) => finding.items.some((item) => item.tier !== 'thap'))
    case 'error': return fixable.filter((finding) => finding.level === 'error')
    case 'warning': return fixable.filter((finding) => finding.level === 'warning' || finding.level === 'info')
    case 'spelling': return fixable.filter((finding) => finding.level === 'spelling')
    case 'none': return []
  }
}

export function quickSelection(pick: QuickPick, findings: Finding[], byId: ItemMap): Set<string> {
  const ids = pickMatches(pick, findings).flatMap((finding) => finding.items.map((item) => item.id))
  return close(new Set(ids), byId)
}

export function sameSet(a: Set<string>, b: Set<string>): boolean {
  if (a.size !== b.size) return false
  for (const value of a) if (!b.has(value)) return false
  return true
}

/* ---------- time and errors ---------- */

/** The server sends ISO UTC with a zone; a value without one is taken as UTC. */
export function parseTime(value: string): number {
  return new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(value) ? value : `${value}Z`).getTime()
}

/** "còn 23 giờ 41 phút" */
export function formatRemaining(expiresAt: string, now: number): string {
  const minutes = Math.floor((parseTime(expiresAt) - now) / 60000)
  if (Number.isNaN(minutes)) return ''
  if (minutes <= 0) return 'đã hết hạn'
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  if (hours === 0) return `còn ${rest} phút`
  return rest === 0 ? `còn ${hours} giờ` : `còn ${hours} giờ ${rest} phút`
}

/** `kind` picks the icon and the next step shown with the message. */
export type FailureKind = 'unsupported' | 'too_large' | 'empty' | 'scan' | 'invalid' | 'gone' | 'network' | 'generic'

export interface FailureText {
  title: string
  message: string
  kind?: FailureKind
}

/** A readable Vietnamese title and message for a failed request (scanned PDF, unsupported or unreadable file, size, network). */
export function describeFailure(error: unknown, fallbackTitle: string): FailureText {
  if (!(error instanceof ApiError)) {
    return { title: fallbackTitle, message: error instanceof Error ? error.message : 'Đã xảy ra lỗi không xác định.' }
  }
  if (error.status === 0) return { title: 'Không kết nối được máy chủ', message: error.message, kind: 'network' }
  if (error.status === 413) return { title: 'Tệp quá lớn', message: error.message, kind: 'too_large' }
  if (error.status === 404) return { title: 'Không còn tệp kiểm tra', message: error.message, kind: 'gone' }
  if (error.status === 422) {
    if (/scan/i.test(error.message) || error.data.scan === true) {
      return { title: 'Bản scan chưa kiểm tra được', message: error.message, kind: 'scan' }
    }
    if (/chỉ nhận tệp/i.test(error.message)) return { title: 'Định dạng tệp chưa được hỗ trợ', message: error.message, kind: 'unsupported' }
    return { title: fallbackTitle, message: error.message, kind: 'invalid' }
  }
  return { title: fallbackTitle, message: error.message, kind: 'generic' }
}
