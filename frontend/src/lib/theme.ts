/** Light / dark theme: stored choice (localStorage `qk3.theme`) or the OS preference, applied as `data-theme` on <html>. */
export type Theme = 'light' | 'dark'

const KEY = 'qk3.theme'
const listeners = new Set<() => void>()

function systemTheme(): Theme {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function storedTheme(): Theme | null {
  try {
    const value = localStorage.getItem(KEY)
    return value === 'light' || value === 'dark' ? value : null
  } catch {
    return null // storage blocked (private window, policy): fall back to the OS preference
  }
}

/** The theme currently shown. The inline script in index.html has already set the attribute before React starts. */
export function getTheme(): Theme {
  const applied = document.documentElement.getAttribute('data-theme')
  return applied === 'dark' || applied === 'light' ? applied : (storedTheme() ?? systemTheme())
}

function apply(theme: Theme): void {
  document.documentElement.setAttribute('data-theme', theme)
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'dark' ? '#0b1220' : '#0a1f44')
  listeners.forEach((listener) => listener())
}

/** Chooses a theme and remembers it. */
export function setTheme(theme: Theme): void {
  try {
    localStorage.setItem(KEY, theme)
  } catch {
    // not persisted; still applied for this page view
  }
  apply(theme)
}

export function toggleTheme(): void {
  setTheme(getTheme() === 'dark' ? 'light' : 'dark')
}

/** For `useSyncExternalStore`. */
export function subscribeTheme(listener: () => void): () => void {
  listeners.add(listener)
  // Follow the OS while the user has not chosen explicitly.
  const media = window.matchMedia?.('(prefers-color-scheme: dark)')
  const onSystem = () => {
    if (storedTheme() === null) apply(systemTheme())
  }
  media?.addEventListener('change', onSystem)
  return () => {
    listeners.delete(listener)
    media?.removeEventListener('change', onSystem)
  }
}
