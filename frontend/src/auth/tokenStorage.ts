const KEY = 'qk3.token'

/** The session token, or null (also when session storage is unavailable). */
export function getToken(): string | null {
  try {
    return sessionStorage.getItem(KEY)
  } catch {
    return null
  }
}

/** Remembers the token for this browser tab only. */
export function setToken(token: string): void {
  try {
    sessionStorage.setItem(KEY, token)
  } catch {
    // Storage blocked: the user simply has to sign in again after a reload.
  }
}

/** Forgets the token. */
export function clearToken(): void {
  try {
    sessionStorage.removeItem(KEY)
  } catch {
    // Nothing to clear.
  }
}
