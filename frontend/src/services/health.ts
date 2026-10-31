import { ApiError, apiFetch } from './api'
import { isHealthResponse } from '../types/api'
import type { HealthSnapshot } from '../types/api'

export async function fetchHealth(signal?: AbortSignal): Promise<HealthSnapshot> {
  const { status, body } = await apiFetch<unknown>('/health', {
    signal,
    acceptStatuses: [503],
  })

  if (!isHealthResponse(body)) {
    throw new ApiError({
      status,
      code: 'invalid_response',
      message: 'The health endpoint returned a payload that does not match the API contract.',
    })
  }

  return {
    health: body,
    httpStatus: status,
    checkedAt: new Date().toISOString(),
  }
}
