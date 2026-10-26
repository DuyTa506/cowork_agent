import { request } from './client'
import type { TokenResponse, User } from './types'

/** POST /api/auth/login */
export function login(username: string, password: string): Promise<TokenResponse> {
  return request<TokenResponse>('/api/auth/login', { method: 'POST', body: { username, password }, auth: false })
}

/** GET /api/auth/me */
export function fetchCurrentUser(signal?: AbortSignal): Promise<User> {
  return request<User>('/api/auth/me', { signal })
}

/** POST /api/auth/change-password */
export function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  return request<void>('/api/auth/change-password', {
    method: 'POST',
    body: { current_password: currentPassword, new_password: newPassword },
  })
}
