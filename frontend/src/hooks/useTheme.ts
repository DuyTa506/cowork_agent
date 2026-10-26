import { useSyncExternalStore } from 'react'
import { getTheme, setTheme, subscribeTheme, toggleTheme, type Theme } from '../lib/theme'

/** Current theme plus setters; re-renders when the theme changes anywhere. */
export function useTheme(): { theme: Theme; setTheme: (theme: Theme) => void; toggle: () => void } {
  const theme = useSyncExternalStore(subscribeTheme, getTheme, () => 'light' as Theme)
  return { theme, setTheme, toggle: toggleTheme }
}
