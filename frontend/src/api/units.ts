import { request } from './client'
import type { Unit } from './types'

/** GET /api/units: the organisation chart as a flat, ordered list with depth. */
export function listUnits(signal?: AbortSignal): Promise<Unit[]> {
  return request<Unit[]>('/api/units', { signal })
}
