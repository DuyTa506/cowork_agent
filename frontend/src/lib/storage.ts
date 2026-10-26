/** localStorage / sessionStorage access that never throws (private windows and locked-down browsers can block it). */
export function readStorage(kind: 'local' | 'session', key: string): string | null {
  try {
    return (kind === 'local' ? localStorage : sessionStorage).getItem(key)
  } catch {
    return null
  }
}

export function writeStorage(kind: 'local' | 'session', key: string, value: string): void {
  try {
    ;(kind === 'local' ? localStorage : sessionStorage).setItem(key, value)
  } catch {
    // ignored: the value just is not remembered
  }
}
