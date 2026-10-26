import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import { NAV } from '../components/layout/nav'
import { useDocumentTitle } from './useDocumentTitle'

export interface Crumb {
  label: string
  /** Makes the crumb a link; the last crumb (the current page) never needs one. */
  to?: string
}

interface PageMetaValue {
  /** Crumbs registered by the current page, or null to use the default for the route. */
  crumbs: Crumb[] | null
  setCrumbs: (crumbs: Crumb[] | null) => void
}

/** First crumb of every trail: the organisation. */
export const ROOT: Crumb = { label: 'Quân khu 3', to: '/kho' }

const PageMetaContext = createContext<PageMetaValue | null>(null)

/** Holds the breadcrumb the top bar shows; `AppShell` mounts it. */
export function PageMetaProvider({ children }: { children: ReactNode }) {
  const [crumbs, setCrumbs] = useState<Crumb[] | null>(null)
  const value = useMemo(() => ({ crumbs, setCrumbs }), [crumbs])
  return <PageMetaContext.Provider value={value}>{children}</PageMetaContext.Provider>
}

/**
 * Sets the browser tab title and the top-bar breadcrumb for a page:
 * `usePageMeta({ title: 'Kho văn bản' })` or `usePageMeta({ title: 'QĐ 12', crumbs: [{ label: 'Kho văn bản', to: '/kho' }, { label: 'QĐ 12' }] })`.
 * The top bar prefixes the trail with "Quân khu 3". Without `crumbs` the trail is the section name from the navigation. Pages that do not call it still get a sensible default.
 */
export function usePageMeta({ title, crumbs }: { title: string; crumbs?: Crumb[] }): void {
  useDocumentTitle(title)
  const ctx = useContext(PageMetaContext)
  const setCrumbs = ctx?.setCrumbs
  const key = JSON.stringify(crumbs ?? null)
  useEffect(() => {
    if (!setCrumbs) return
    setCrumbs(JSON.parse(key) as Crumb[] | null)
    return () => setCrumbs(null)
  }, [setCrumbs, key])
}

/** Crumbs for the top bar: what the page registered, else derived from the route. */
export function useCrumbs(): Crumb[] {
  const ctx = useContext(PageMetaContext)
  const { pathname } = useLocation()
  if (ctx?.crumbs) return [ROOT, ...ctx.crumbs]
  const section = NAV.find((entry) => pathname === entry.to || pathname.startsWith(`${entry.to}/`))
  if (!section) return [ROOT, { label: 'Không tìm thấy trang' }]
  return pathname === section.to ? [ROOT, { label: section.label }] : [ROOT, { label: section.label, to: section.to }, { label: 'Chi tiết' }]
}
