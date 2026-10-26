import { request } from './client'
import type {
  AuditEntry,
  ReindexResult,
  SaveSettingsResult,
  SettingsOverview,
  SettingsPayload,
  TestConnectionResult,
  User,
  UserCreate,
  UserUpdate,
} from './types'

/** GET /api/admin/users */
export function listUsers(signal?: AbortSignal): Promise<User[]> {
  return request<User[]>('/api/admin/users', { signal })
}

/** POST /api/admin/users */
export function createUser(body: UserCreate): Promise<User> {
  return request<User>('/api/admin/users', { method: 'POST', body })
}

/** PATCH /api/admin/users/{id}; omitted fields stay unchanged. */
export function updateUser(id: number, body: UserUpdate): Promise<User> {
  return request<User>(`/api/admin/users/${id}`, { method: 'PATCH', body })
}

export interface AuditQuery {
  /** Action prefix such as `document` or `settings.save`. */
  action?: string
  username?: string
  limit: number
  offset: number
}

/** GET /api/admin/audit-logs (newest first). */
export function listAuditLogs(query: AuditQuery, signal?: AbortSignal): Promise<AuditEntry[]> {
  return request<AuditEntry[]>('/api/admin/audit-logs', {
    query: { action: query.action, username: query.username, limit: query.limit, offset: query.offset },
    signal,
  })
}

/** GET /api/admin/settings */
export function getSettings(signal?: AbortSignal): Promise<SettingsOverview> {
  return request<SettingsOverview>('/api/admin/settings', { signal })
}

/** PUT /api/admin/settings/{section}. Throws `ApiError` with code `external_endpoint` when hosts need confirming. */
export function saveSettings(section: string, values: SettingsPayload, confirmHosts: string[]): Promise<SaveSettingsResult> {
  return request<SaveSettingsResult>(`/api/admin/settings/${section}`, {
    method: 'PUT',
    body: { values, confirm_hosts: confirmHosts },
  })
}

/** POST /api/admin/settings/{section}/test: tries the values without saving them. */
export function testSettings(section: string, values: SettingsPayload): Promise<TestConnectionResult> {
  return request<TestConnectionResult>(`/api/admin/settings/${section}/test`, { method: 'POST', body: { values } })
}

/** POST /api/admin/reindex */
export function reindexAll(): Promise<ReindexResult> {
  return request<ReindexResult>('/api/admin/reindex', { method: 'POST' })
}
