import { isApiErrorBody } from '../types/api'
import type { ApiErrorDetail } from '../types/api'

const FALLBACK_BASE_URL = 'http://localhost:8000'
const DEFAULT_TIMEOUT_MS = 10_000

function resolveBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL
  const base =
    typeof configured === 'string' && configured.trim().length > 0
      ? configured.trim()
      : FALLBACK_BASE_URL

  return base.replace(/\/+$/, '')
}

export const API_BASE_URL = resolveBaseUrl()

interface ApiErrorParams {
  status: number
  code: string
  message: string
  requestId?: string | null
  details?: ApiErrorDetail[]
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly requestId: string | null
  readonly details: ApiErrorDetail[]

  constructor(params: ApiErrorParams) {
    super(params.message)
    this.name = 'ApiError'
    this.status = params.status
    this.code = params.code
    this.requestId = params.requestId ?? null
    this.details = params.details ?? []
  }
}

export interface ApiRequestOptions {
  method?: string
  body?: BodyInit | null
  headers?: Record<string, string>
  signal?: AbortSignal
  timeoutMs?: number
  acceptStatuses?: number[]
}

export interface ApiResponse<T> {
  status: number
  body: T
}

async function readJson(response: Response): Promise<unknown> {
  const contentType = response.headers.get('Content-Type') ?? ''

  if (!contentType.includes('json')) {
    return null
  }

  try {
    return (await response.json()) as unknown
  } catch {
    return null
  }
}

function toApiError(status: number, payload: unknown, headerRequestId: string | null): ApiError {
  if (isApiErrorBody(payload)) {
    return new ApiError({
      status,
      code: payload.error.code,
      message: payload.error.message,
      requestId: payload.error.request_id ?? headerRequestId,
      details: payload.error.details ?? [],
    })
  }

  return new ApiError({
    status,
    code: status >= 500 ? 'internal_error' : 'unexpected_response',
    message: `The API returned an unexpected ${status} response.`,
    requestId: headerRequestId,
  })
}

export async function apiFetch<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<ApiResponse<T>> {
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS
  const controller = new AbortController()
  const timer = window.setTimeout(() => {
    controller.abort()
  }, timeoutMs)

  const parentSignal = options.signal
  const forwardAbort = (): void => {
    controller.abort()
  }

  if (parentSignal) {
    if (parentSignal.aborted) {
      controller.abort()
    } else {
      parentSignal.addEventListener('abort', forwardAbort, { once: true })
    }
  }

  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...options.headers,
  }

  if (options.body !== undefined && options.body !== null) {
    headers['Content-Type'] = `application/json`
  }

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: options.method ?? 'GET',
      headers,
      body: options.body ?? null,
      signal: controller.signal,
      credentials: 'omit',
    })

    const payload = await readJson(response)
    const acceptedStatuses = options.acceptStatuses ?? []

    if (!response.ok && !acceptedStatuses.includes(response.status)) {
      throw toApiError(response.status, payload, response.headers.get('X-Request-ID'))
    }

    return { status: response.status, body: payload as T }
  } catch (error) {
    if (error instanceof ApiError) {
      throw error
    }

    if (parentSignal?.aborted) {
      throw new ApiError({
        status: 0,
        code: 'cancelled',
        message: 'The request was cancelled.',
      })
    }

    if (controller.signal.aborted) {
      throw new ApiError({
        status: 0,
        code: 'timeout',
        message: `The API did not respond within ${Math.round(timeoutMs / 1000)} seconds.`,
      })
    }

    throw new ApiError({
      status: 0,
      code: 'network_error',
      message: 'Could not reach the POTENCIA API. The backend may not be running.',
    })
  } finally {
    window.clearTimeout(timer)
    parentSignal?.removeEventListener('abort', forwardAbort)
  }
}
