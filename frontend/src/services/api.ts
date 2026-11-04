import { isApiErrorBody } from '../types/api'
import type { ApiErrorDetail } from '../types/api'

const FALLBACK_BASE_URL = 'http://localhost:8000'
const DEFAULT_TIMEOUT_MS = 10_000

function cleanBase(val: string): string {
  let base = val.trim().replace(/\/+$/, '')
  // Strip trailing /api/v1 or /api if the user provided it in VITE_API_BASE_URL
  if (base.endsWith('/api/v1')) {
    base = base.slice(0, -'/api/v1'.length)
  } else if (base.endsWith('/api')) {
    base = base.slice(0, -'/api'.length)
  }
  return base.replace(/\/+$/, '')
}

export function resolveBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL
  if (typeof configured === 'string' && configured.trim().length > 0) {
    return cleanBase(configured)
  }
  return FALLBACK_BASE_URL
}

export const API_BASE_URL = resolveBaseUrl()

/**
 * Build a canonical, fully-qualified URL for an API request path.
 * Guarantees that:
 * 1. Slashes between base and path are correctly joined.
 * 2. If path is e.g. /api/v1/auth/register and base was https://..., it does not duplicate /api/v1.
 * 3. If path is /health, it correctly resolves to https://.../health.
 */
export function buildApiUrl(path: string, customBase?: string): string {
  const base = customBase !== undefined ? cleanBase(customBase) : resolveBaseUrl()
  const cleanPath = path.startsWith('/') ? path : `/${path}`

  // Guard against duplicated /api/v1 prefix
  if (base.endsWith('/api/v1') && cleanPath.startsWith('/api/v1/')) {
    return `${base}${cleanPath.slice('/api/v1'.length)}`
  }

  // Guard against duplicated /api/v1/api/v1 in cleanPath
  const normalizedPath = cleanPath.replace(/^\/api\/v1\/api\/v1\//, '/api/v1/')

  return `${base}${normalizedPath}`
}

export interface DiagnosticLogData {
  url: string
  method: string
  status?: number
  category?: string
  requestId?: string | null
  details?: string
}

export function logDiagnostic(
  level: 'info' | 'warn' | 'error',
  data: DiagnosticLogData,
): void {
  // Never log passwords, tokens, API keys, or raw personal request bodies
  const tag = `[POTENCIA API ${data.method.toUpperCase()}]`
  const statusStr = data.status !== undefined ? `status: ${data.status}` : 'network_error'
  const categoryStr = data.category ? `[${data.category}]` : ''
  const reqStr = data.requestId ? `(req_id: ${data.requestId})` : ''
  const detailsStr = data.details ? `— ${data.details}` : ''

  const line = [
    `${tag} ${data.url} | ${statusStr}`,
    categoryStr,
    reqStr,
    detailsStr,
  ].filter(Boolean).join(' ')

  if (level === 'error') {
    console.error(line)
  } else if (level === 'warn') {
    console.warn(line)
  } else {
    console.info(line)
  }
}

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
  credentials?: RequestCredentials
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
    let customMessage = payload.error.message

    // Provide friendly, actionable messages for key status codes if message is generic
    if (status === 400) {
      customMessage = payload.error.message || 'Invalid request. Please check your submission and try again.'
    } else if (status === 409) {
      customMessage = payload.error.message || 'That email address is already registered. Please sign in or use another email.'
    } else if (status === 422) {
      if (payload.error.details && payload.error.details.length > 0) {
        const fieldIssues = payload.error.details
          .map((d) => (d.field ? `${d.field}: ${d.meta?.message || d.issue}` : d.meta?.message || d.issue))
          .filter(Boolean)
          .join(', ')
        if (fieldIssues) {
          customMessage = `Please check your input: ${fieldIssues}`
        }
      }
      if (!customMessage || customMessage === 'The request body or parameters are invalid.') {
        customMessage = 'Please check your information: email format must be valid and password must be at least 12 characters.'
      }
    } else if (status === 429) {
      customMessage = payload.error.message || 'Too many requests. Please wait a few minutes before trying again.'
    } else if (status >= 500) {
      customMessage = 'The server encountered an error while processing your request. Please try again shortly.'
    }

    return new ApiError({
      status,
      code: payload.error.code,
      message: customMessage,
      requestId: payload.error.request_id ?? headerRequestId,
      details: payload.error.details ?? [],
    })
  }

  // Non-JSON or unexpected error format (e.g. proxy HTML response or unhandled status)
  let fallbackCode = status >= 500 ? 'internal_error' : 'unexpected_response'
  let fallbackMessage = `The API returned an unexpected ${status} response.`

  if (status === 400) {
    fallbackCode = 'bad_request'
    fallbackMessage = 'The request was invalid. Please check your submission and try again.'
  } else if (status === 401) {
    fallbackCode = 'unauthenticated'
    fallbackMessage = 'Authentication required. Please sign in.'
  } else if (status === 403) {
    fallbackCode = 'forbidden'
    fallbackMessage = 'Access denied. You do not have permission for this action.'
  } else if (status === 404) {
    fallbackCode = 'not_found'
    fallbackMessage = 'The requested endpoint was not found on the server. Please check the API configuration.'
  } else if (status === 409) {
    fallbackCode = 'conflict'
    fallbackMessage = 'An account with that email address already exists. Please sign in.'
  } else if (status === 422) {
    fallbackCode = 'validation_error'
    fallbackMessage = 'Validation failed. Please ensure your email is valid and password is at least 12 characters.'
  } else if (status === 429) {
    fallbackCode = 'rate_limited'
    fallbackMessage = 'Too many attempts. Please slow down and try again later.'
  } else if (status === 502 || status === 503 || status === 504) {
    fallbackCode = 'service_unavailable'
    fallbackMessage = 'The POTENCIA backend is temporarily unavailable or starting up. Please retry in 30 seconds.'
  } else if (status >= 500) {
    fallbackCode = 'internal_error'
    fallbackMessage = 'The server encountered an error. Please try again in a few moments.'
  }

  return new ApiError({
    status,
    code: fallbackCode,
    message: fallbackMessage,
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

  const targetUrl = buildApiUrl(path)

  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...options.headers,
  }

  if (options.body !== undefined && options.body !== null) {
    headers['Content-Type'] = 'application/json'
  }

  logDiagnostic('info', {
    url: targetUrl,
    method: options.method ?? 'GET',
  })

  try {
    const response = await fetch(targetUrl, {
      method: options.method ?? 'GET',
      headers,
      body: options.body ?? null,
      signal: controller.signal,
      credentials: options.credentials ?? 'same-origin',
    })

    const payload = await readJson(response)
    const acceptedStatuses = options.acceptStatuses ?? []

    if (!response.ok && !acceptedStatuses.includes(response.status)) {
      const apiErr = toApiError(response.status, payload, response.headers.get('X-Request-ID'))
      logDiagnostic('error', {
        url: targetUrl,
        method: options.method ?? 'GET',
        status: response.status,
        category: apiErr.code,
        requestId: apiErr.requestId,
        details: apiErr.message,
      })
      throw apiErr
    }

    logDiagnostic('info', {
      url: targetUrl,
      method: options.method ?? 'GET',
      status: response.status,
      requestId: response.headers.get('X-Request-ID'),
    })

    return { status: response.status, body: payload as T }
  } catch (error) {
    if (error instanceof ApiError) {
      throw error
    }

    if (parentSignal?.aborted) {
      const err = new ApiError({
        status: 0,
        code: 'cancelled',
        message: 'The request was cancelled.',
      })
      logDiagnostic('warn', {
        url: targetUrl,
        method: options.method ?? 'GET',
        status: 0,
        category: 'cancelled',
      })
      throw err
    }

    if (controller.signal.aborted) {
      const err = new ApiError({
        status: 0,
        code: 'timeout',
        message: `The API did not respond within ${Math.round(timeoutMs / 1000)} seconds. The server might be asleep or spinning up.`,
      })
      logDiagnostic('error', {
        url: targetUrl,
        method: options.method ?? 'GET',
        status: 0,
        category: 'timeout',
      })
      throw err
    }

    // Inspect the error and runtime environment to provide an accurate diagnosis
    const errorMsg = error instanceof Error ? error.message : String(error)
    const isHttpsPage = typeof window !== 'undefined' && window.location.protocol === 'https:'
    const isTargetHttp = targetUrl.startsWith('http://')
    const isTargetLocalhost = targetUrl.includes('localhost') || targetUrl.includes('127.0.0.1')
    const isRemotePage = typeof window !== 'undefined' && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1'

    let code = 'network_error'
    let message = 'Could not reach the POTENCIA API. The backend may not be running.'

    if (isHttpsPage && isTargetHttp) {
      code = 'mixed_content_blocked'
      message = `Browser blocked connection: The website is on HTTPS (${window.location.origin}), but tried to call unencrypted HTTP (${targetUrl}). Please set VITE_API_BASE_URL to an https:// URL.`
    } else if (isRemotePage && isTargetLocalhost) {
      code = 'misconfigured_api_url'
      message = `Configuration error: The app is deployed on ${window.location.hostname}, but trying to connect to localhost (${targetUrl}). Please set VITE_API_BASE_URL to your backend Render URL.`
    } else if (errorMsg.toLowerCase().includes('failed to fetch') || errorMsg.toLowerCase().includes('networkerror')) {
      code = 'cors_or_network_failure'
      message = `Could not connect to ${targetUrl}. Possible causes: CORS origin mismatch, network interruption, or the backend is still starting up.`
    } else {
      code = 'network_failure'
      message = `Network failure communicating with ${targetUrl}: ${errorMsg}`
    }

    logDiagnostic('error', {
      url: targetUrl,
      method: options.method ?? 'GET',
      status: 0,
      category: code,
      details: errorMsg,
    })

    throw new ApiError({
      status: 0,
      code,
      message,
    })
  } finally {
    window.clearTimeout(timer)
    parentSignal?.removeEventListener('abort', forwardAbort)
  }
}
