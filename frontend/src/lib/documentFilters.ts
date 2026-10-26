import type { DocumentLevel } from '../api'
import type { StateTabKey } from './documents'

/** Everything the Kho list can be narrowed by. The whole thing lives in the URL, so a view can be shared. */
export interface DocumentFilters {
  q: string
  /** Chosen types: a document matches any of them. */
  types: string[]
  unitId: string
  level: '' | DocumentLevel
  /** ISO dates; a year chip sets both to the first and last day of that year. */
  dateFrom: string
  dateTo: string
  /** A document must carry every one of these. */
  tags: string[]
}

export interface ListView {
  filters: DocumentFilters
  tab: StateTabKey
  /** Zero-based page. */
  page: number
}

export const EMPTY_FILTERS: DocumentFilters = { q: '', types: [], unitId: '', level: '', dateFrom: '', dateTo: '', tags: [] }

const TABS: StateTabKey[] = ['all', 'ready', 'processing', 'review', 'attention']
const ISO = /^\d{4}-\d{2}-\d{2}$/

/** Reads the list view from the query string; unknown or malformed values fall back to "no filter". */
export function readView(params: URLSearchParams): ListView {
  const tab = params.get('st') as StateTabKey | null
  const level = params.get('lv')
  const date = (key: string) => (ISO.test(params.get(key) ?? '') ? (params.get(key) as string) : '')
  const page = Number(params.get('p'))
  return {
    filters: {
      q: params.get('q') ?? '',
      types: (params.get('tp') ?? '').split('|').filter(Boolean),
      unitId: params.get('u') ?? '',
      level: level === 'thuong' || level === 'mat' ? level : '',
      dateFrom: date('from'),
      dateTo: date('to'),
      tags: params.getAll('tag').filter(Boolean),
    },
    tab: tab && TABS.includes(tab) ? tab : 'all',
    page: Number.isInteger(page) && page > 0 ? page : 0,
  }
}

/** The query string for a list view (defaults are left out so the address stays short). */
export function writeView(view: ListView): URLSearchParams {
  const { filters, tab, page } = view
  const params = new URLSearchParams()
  if (filters.q) params.set('q', filters.q)
  if (filters.types.length > 0) params.set('tp', filters.types.join('|'))
  if (filters.unitId) params.set('u', filters.unitId)
  if (filters.level) params.set('lv', filters.level)
  if (filters.dateFrom) params.set('from', filters.dateFrom)
  if (filters.dateTo) params.set('to', filters.dateTo)
  filters.tags.forEach((tag) => params.append('tag', tag))
  if (tab !== 'all') params.set('st', tab)
  if (page > 0) params.set('p', String(page))
  return params
}

/** The year a date range covers exactly ("2025-01-01" to "2025-12-31"), or '' for any other range. */
export function yearOf(filters: Pick<DocumentFilters, 'dateFrom' | 'dateTo'>): string {
  const year = filters.dateFrom.slice(0, 4)
  return year && filters.dateFrom === `${year}-01-01` && filters.dateTo === `${year}-12-31` ? year : ''
}

export function yearRange(year: string): Pick<DocumentFilters, 'dateFrom' | 'dateTo'> {
  return { dateFrom: `${year}-01-01`, dateTo: `${year}-12-31` }
}

/** Tags the browse panel offers: the year tags are left out because the "Năm" group already filters by issue date. */
export function isYearTag(tag: string): boolean {
  return /^Năm \d{4}$/.test(tag)
}

/** True when any filter (not the state card) is set. */
export function hasFilters(filters: DocumentFilters): boolean {
  return Boolean(filters.q || filters.types.length || filters.unitId || filters.level || filters.dateFrom || filters.dateTo || filters.tags.length)
}
