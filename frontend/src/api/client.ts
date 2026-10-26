import { clearToken, getToken } from '../auth/tokenStorage'

/** Error returned by the API (`{detail, code?, ...}`) or raised when the server cannot be reached (status 0). */
export class ApiError extends Error {
  readonly status: number
  readonly code: string | undefined
  /** The whole JSON error body, for extra fields such as `hosts` or `document_id`. */
  readonly data: Record<string, unknown>

  constructor(message: string, status: number, data: Record<string, unknown> = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.data = data
    this.code = typeof data.code === 'string' ? data.code : undefined
  }
}

type QueryValue = string | number | boolean | string[] | undefined
type UnauthorizedHandler = () => void

let unauthorizedHandler: UnauthorizedHandler | null = null

/** Registers what happens when an authenticated request is rejected with 401 (the session ended). */
export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  query?: Record<string, QueryValue>
  /** JSON body. */
  body?: unknown
  signal?: AbortSignal
  /** Set to false for requests made before sign-in (login): no token, and a 401 is just a wrong password. */
  auth?: boolean
}

function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  if (!query) return path
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (Array.isArray(value)) value.forEach((item) => params.append(key, item))
    else if (value !== undefined && value !== '') params.set(key, String(value))
  }
  const text = params.toString()
  return text ? `${path}?${text}` : path
}

/** Turns FastAPI's `detail` (string or list of validation errors) into one readable message. */
function messageFrom(data: Record<string, unknown>, status: number): string {
  const detail = data.detail
  if (typeof detail === 'string' && detail) return detail
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: unknown }
    return typeof first.msg === 'string' ? `Dữ liệu không hợp lệ: ${first.msg}` : 'Dữ liệu không hợp lệ.'
  }
  if (status === 413) return 'Tệp quá lớn.'
  return `Yêu cầu thất bại (mã ${status}).`
}

async function toApiError(response: Response, authenticated: boolean): Promise<ApiError> {
  let data: Record<string, unknown> = {}
  try {
    const parsed: unknown = await response.json()
    if (parsed && typeof parsed === 'object') data = parsed as Record<string, unknown>
  } catch {
    // Non-JSON error body (for example a proxy page): fall back to the generic message.
  }
  if (response.status === 401 && authenticated) {
    clearToken()
    unauthorizedHandler?.()
  }
  return new ApiError(messageFrom(data, response.status), response.status, data)
}

function authHeaders(authenticated: boolean): Record<string, string> {
  const token = authenticated ? getToken() : null
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function send(path: string, options: RequestOptions, extraHeaders: Record<string, string> = {}): Promise<Response> {
  const authenticated = options.auth !== false
  let response: Response
  try {
    response = await fetch(buildUrl(path, options.query), {
      method: options.method ?? 'GET',
      headers: { ...authHeaders(authenticated), ...extraHeaders },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError('Không kết nối được máy chủ. Kiểm tra mạng nội bộ rồi thử lại.', 0)
  }
  if (!response.ok) throw await toApiError(response, authenticated)
  return response
}

/** Calls the API and parses the JSON response (`undefined` for 204). */
export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = options.body === undefined ? {} : { 'Content-Type': 'application/json' }
  const response = await send(path, options, headers)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

/** Fetches a binary response (for example the original file) with the session token. */
export async function requestBlob(path: string, signal?: AbortSignal): Promise<Blob> {
  const response = await send(path, { signal })
  return response.blob()
}

/**
 * POSTs multipart form data and reports upload progress (fetch cannot, so XMLHttpRequest is used).
 * @param onProgress called with a fraction between 0 and 1 while the request body is being sent.
 */
export function uploadForm<T>(path: string, form: FormData, onProgress: (fraction: number) => void): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', path)
    for (const [name, value] of Object.entries(authHeaders(true))) xhr.setRequestHeader(name, value)
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total)
    }
    xhr.onerror = () => reject(new ApiError('Không kết nối được máy chủ. Kiểm tra mạng nội bộ rồi thử lại.', 0))
    xhr.onload = () => {
      let data: unknown = {}
      try {
        data = JSON.parse(xhr.responseText)
      } catch {
        // Empty or non-JSON body.
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(data as T)
        return
      }
      const body = data && typeof data === 'object' ? (data as Record<string, unknown>) : {}
      if (xhr.status === 401) {
        clearToken()
        unauthorizedHandler?.()
      }
      reject(new ApiError(messageFrom(body, xhr.status), xhr.status, body))
    }
    xhr.send(form)
  })
}
