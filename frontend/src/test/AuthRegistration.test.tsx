import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { buildApiUrl, ApiError, logDiagnostic } from '../services/api'
import { register } from '../services/auth'

describe('Registration API Configuration & URL Normalization', () => {
  it('correctly builds API URL with standard base without trailing slash', () => {
    const url = buildApiUrl('/api/v1/auth/register', 'https://potencia-api-tnf1.onrender.com')
    expect(url).toBe('https://potencia-api-tnf1.onrender.com/api/v1/auth/register')
  })

  it('correctly builds API URL when base has a trailing slash', () => {
    const url = buildApiUrl('/api/v1/auth/register', 'https://potencia-api-tnf1.onrender.com/')
    expect(url).toBe('https://potencia-api-tnf1.onrender.com/api/v1/auth/register')
  })

  it('prevents duplicated /api/v1 when VITE_API_BASE_URL includes /api/v1', () => {
    const url = buildApiUrl('/api/v1/auth/register', 'https://potencia-api-tnf1.onrender.com/api/v1')
    expect(url).toBe('https://potencia-api-tnf1.onrender.com/api/v1/auth/register')
  })

  it('prevents duplicated /api/v1 when VITE_API_BASE_URL includes /api/v1/ with trailing slash', () => {
    const url = buildApiUrl('/api/v1/auth/register', 'https://potencia-api-tnf1.onrender.com/api/v1/')
    expect(url).toBe('https://potencia-api-tnf1.onrender.com/api/v1/auth/register')
  })

  it('prevents duplicated /api when VITE_API_BASE_URL includes /api', () => {
    const url = buildApiUrl('/api/v1/auth/register', 'https://potencia-api-tnf1.onrender.com/api')
    expect(url).toBe('https://potencia-api-tnf1.onrender.com/api/v1/auth/register')
  })

  it('correctly handles root-level endpoints like /health when base includes /api/v1', () => {
    const url = buildApiUrl('/health', 'https://potencia-api-tnf1.onrender.com/api/v1')
    expect(url).toBe('https://potencia-api-tnf1.onrender.com/health')
  })

  it('handles paths without leading slash gracefully', () => {
    const url = buildApiUrl('api/v1/auth/register', 'https://potencia-api-tnf1.onrender.com')
    expect(url).toBe('https://potencia-api-tnf1.onrender.com/api/v1/auth/register')
  })
})

describe('Registration Request Execution & Error Handling', () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    vi.restoreAllMocks()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it('executes POST request with application/json headers and matching payload', async () => {
    const mockResponse = {
      user: {
        id: 'usr_123',
        email: 'applicant@example.com',
        display_name: 'Applicant User',
        created_at: new Date().toISOString(),
        email_verified: false,
      },
      tokens: {
        access_token: 'acc_token_xyz',
        refresh_token: 'ref_token_xyz',
        token_type: 'bearer',
        expires_in: 900,
      },
    }

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      headers: new Headers({ 'Content-Type': 'application/json', 'X-Request-ID': 'req_test_1' }),
      json: async () => mockResponse,
    })
    globalThis.fetch = fetchMock

    const res = await register({
      email: 'applicant@example.com',
      password: 'SecurePassword123!',
      display_name: 'Applicant User',
    })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const call = (fetchMock.mock.calls as Array<[string, RequestInit]>)[0]!
    const [callUrl, callOptions] = call
    expect(callUrl).toContain('/api/v1/auth/register')
    expect(callOptions.method).toBe('POST')
    expect((callOptions.headers as Record<string, string>)['Content-Type']).toBe('application/json')
    expect((callOptions.headers as Record<string, string>)['Accept']).toBe('application/json')
    expect((callOptions.headers as Record<string, string>)['Authorization']).toBeUndefined()

    const sentBody = JSON.parse(callOptions.body as string)
    expect(sentBody.email).toBe('applicant@example.com')
    expect(sentBody.password).toBe('SecurePassword123!')
    expect(sentBody.display_name).toBe('Applicant User')

    expect(res.user.email).toBe('applicant@example.com')
    expect(res.tokens.access_token).toBe('acc_token_xyz')
  })

  it('handles HTTP 409 Conflict with dedicated error message without hiding backend reason', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      headers: new Headers({ 'Content-Type': 'application/json', 'X-Request-ID': 'req_409' }),
      json: async () => ({
        error: {
          code: 'conflict',
          message: 'That email address is already registered.',
          details: [],
          request_id: 'req_409',
        },
      }),
    })

    await expect(
      register({ email: 'existing@example.com', password: 'Password12345!' }),
    ).rejects.toThrow('That email address is already registered.')
  })

  it('handles HTTP 422 Validation Error with detailed field messages', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      headers: new Headers({ 'Content-Type': 'application/json', 'X-Request-ID': 'req_422' }),
      json: async () => ({
        error: {
          code: 'validation_error',
          message: 'The request body or parameters are invalid.',
          details: [
            { field: 'password', issue: 'string_too_short', meta: { message: 'String should have at least 12 characters' } },
          ],
          request_id: 'req_422',
        },
      }),
    })

    await expect(
      register({ email: 'short@example.com', password: 'short' }),
    ).rejects.toThrow(/password: String should have at least 12 characters/i)
  })

  it('handles HTTP 429 Rate Limit with user-friendly retry advice', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 429,
      headers: new Headers({ 'Content-Type': 'application/json', 'X-Request-ID': 'req_429' }),
      json: async () => ({
        error: {
          code: 'rate_limited',
          message: 'Too many requests. Please slow down.',
          details: [],
          request_id: 'req_429',
        },
      }),
    })

    await expect(
      register({ email: 'fast@example.com', password: 'Password12345!' }),
    ).rejects.toThrow(/Too many requests/i)
  })

  it('handles HTTP 500 Internal Error cleanly without exposing raw stack traces', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      headers: new Headers({ 'Content-Type': 'application/json', 'X-Request-ID': 'req_500' }),
      json: async () => ({
        error: {
          code: 'internal_error',
          message: 'An unexpected error occurred. The issue has been logged.',
          details: [],
          request_id: 'req_500',
        },
      }),
    })

    try {
      await register({ email: 'dbfail@example.com', password: 'Password12345!' })
      expect.fail('Should have thrown an error')
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError)
      const apiErr = err as ApiError
      expect(apiErr.status).toBe(500)
      expect(apiErr.code).toBe('internal_error')
      expect(apiErr.requestId).toBe('req_500')
      expect(apiErr.message).not.toContain('Traceback')
      expect(apiErr.message).not.toContain('psycopg')
    }
  })

  it('provides actionable error message on CORS / Network failure', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))

    try {
      await register({ email: 'network@example.com', password: 'Password12345!' })
      expect.fail('Should have thrown an error')
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError)
      const apiErr = err as ApiError
      expect(apiErr.status).toBe(0)
      expect(apiErr.code).toBe('cors_or_network_failure')
      expect(apiErr.message).toContain('Possible causes: CORS origin mismatch, network interruption')
    }
  })

  it('diagnostic logging emits safe summary without exposing sensitive credentials', () => {
    const consoleInfoSpy = vi.spyOn(console, 'info').mockImplementation(() => {})
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    logDiagnostic('info', {
      url: 'https://potencia-api-tnf1.onrender.com/api/v1/auth/register',
      method: 'POST',
      status: 201,
      requestId: 'req_test_123',
    })

    expect(consoleInfoSpy).toHaveBeenCalledWith(
      expect.stringContaining('[POTENCIA API POST] https://potencia-api-tnf1.onrender.com/api/v1/auth/register | status: 201 (req_id: req_test_123)'),
    )

    logDiagnostic('error', {
      url: 'https://potencia-api-tnf1.onrender.com/api/v1/auth/register',
      method: 'POST',
      status: 409,
      category: 'conflict',
      details: 'That email address is already registered.',
    })

    expect(consoleErrorSpy).toHaveBeenCalledWith(
      expect.stringContaining('[POTENCIA API POST] https://potencia-api-tnf1.onrender.com/api/v1/auth/register | status: 409 [conflict] — That email address is already registered.'),
    )

    consoleInfoSpy.mockRestore()
    consoleErrorSpy.mockRestore()
  })
})
