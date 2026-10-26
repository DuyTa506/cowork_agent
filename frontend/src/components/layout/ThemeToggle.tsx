import { useTheme } from '../../hooks/useTheme'
import { IconButton } from '../IconButton'

/** Sun / moon button that switches between the light and dark theme and remembers the choice. */
export function ThemeToggle({ className }: { className?: string }) {
  const { theme, toggle } = useTheme()
  const dark = theme === 'dark'
  return <IconButton icon={dark ? 'sun' : 'moon'} label={dark ? 'Chuyển sang giao diện sáng' : 'Chuyển sang giao diện tối'} onClick={toggle} className={className} />
}
