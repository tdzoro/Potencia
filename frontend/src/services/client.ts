/**
 * Authenticated HTTP client.
 *
 * The access token is short-lived (15 minutes), so the client refreshes it once
 * per failed request rather than on a timer: a refresh that fires while the tab
 * is asleep wastes a rotation, and a rotation that fails must log the user out
 * rather than loop.
 */

import { ApiError, apiFetch, buildApiUrl } from './api'
import type { TokenPair } from '../types/domain'

const ACCESS_KEY = 'potencia.access_token'
const REFRESH_KEY = 'potencia.refresh_token'

export interface Session {
  accessToken: string
  refreshToken: string
}

export function readSession(): Session | null {
  try {
    const accessToken = window.localStorage.getItem(ACCESS_KEY)
    const refreshToken = window.localStorage.getItem(REFRESH_KEY)
    if (!accessToken || !refreshToken) {
      return null
    }
    return { accessToken, refreshToken }
  } catch {
    return null
  }
}

export function writeSession(tokens: TokenPair): void {
  try {
    window.localStorage.setItem(ACCESS_KEY, tokens.access_token)
    window.localStorage.setItem(REFRESH_KEY, tokens.refresh_token)
  } catch {
    // Private browsing can refuse storage; the session then lasts one page view.
  }
}

export function clearSession(): void {
  try {
    window.localStorage.removeItem(ACCESS_KEY)
    window.localStorage.removeItem(REFRESH_KEY)
  } catch {
    // Ignore: there is nothing to clear.
  }
}

let refreshInFlight: Promise<Session | null> | null = null

/** Rotate the token pair once, sharing the attempt across concurrent callers. */
async function refreshSession(): Promise<Session | null> {
  const current = readSession()
  if (!current) {
    return null
  }

  if (!refreshInFlight) {
    refreshInFlight = apiFetch<TokenPair>('/api/v1/auth/refresh', {
      method: 'POST',
      body: JSON.stringify({ refresh_token: current.refreshToken }),
    })
      .then(({ body }) => {
        writeSession(body)
        return { accessToken: body.access_token, refreshToken: body.refresh_token }
      })
      .catch(() => {
        clearSession()
        return null
      })
      .finally(() => {
        refreshInFlight = null
      })
  }

  return refreshInFlight
}

export interface RequestOptions {
  method?: string
  body?: unknown
  signal?: AbortSignal
  timeoutMs?: number
}

async function send<T>(path: string, options: RequestOptions, accessToken: string): Promise<T> {
  const { body } = await apiFetch<T>(path, {
    method: options.method ?? 'GET',
    body: options.body === undefined ? null : JSON.stringify(options.body),
    signal: options.signal,
    timeoutMs: options.timeoutMs,
    headers: { Authorization: `Bearer ${accessToken}` },
  })
  return body
}

/** A request that carries the access token and recovers once from expiry. */
export async function authedRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const session = readSession()
  if (!session) {
    throw new ApiError({ status: 401, code: 'unauthenticated', message: 'Sign in to continue.' })
  }

  try {
    return await send<T>(path, options, session.accessToken)
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401) {
      throw error
    }

    const refreshed = await refreshSession()
    if (!refreshed) {
      throw error
    }
    return send<T>(path, options, refreshed.accessToken)
  }
}

/** Upload a file as multipart form data, with the same refresh behaviour. */
export async function authedUpload<T>(path: string, file: File): Promise<T> {
  const attempt = async (accessToken: string): Promise<Response> => {
    const form = new FormData()
    form.append('file', file)
    return fetch(buildApiUrl(path), {
      method: 'POST',
      headers: { Authorization: `Bearer ${accessToken}`, Accept: 'application/json' },
      body: form,
      credentials: 'same-origin',
    })
  }

  const parse = async (response: Response): Promise<T> => {
    const payload = (await response.json().catch(() => null)) as unknown
    if (!response.ok) {
      const envelope = payload as { error?: { code?: string; message?: string; request_id?: string } }
      throw new ApiError({
        status: response.status,
        code: envelope?.error?.code ?? 'unexpected_response',
        message: envelope?.error?.message ?? `Upload failed with ${response.status}.`,
        requestId: envelope?.error?.request_id ?? null,
      })
    }
    return payload as T
  }

  const session = readSession()
  if (!session) {
    throw new ApiError({ status: 401, code: 'unauthenticated', message: 'Sign in to continue.' })
  }

  let response = await attempt(session.accessToken)
  if (response.status === 401) {
    const refreshed = await refreshSession()
    if (!refreshed) {
      throw new ApiError({ status: 401, code: 'unauthenticated', message: 'Sign in to continue.' })
    }
    response = await attempt(refreshed.accessToken)
  }

  // Uploads can take longer than the default timeout for large documents.
  return parse(response)
}
