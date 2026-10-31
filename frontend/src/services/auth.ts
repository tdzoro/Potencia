import { apiFetch } from './api'
import { authedRequest, clearSession, readSession, writeSession } from './client'
import type { AuthResponse, TokenPair, User } from '../types/domain'

export async function register(input: {
  email: string
  password: string
  display_name?: string
}): Promise<AuthResponse> {
  const { body } = await apiFetch<AuthResponse>('/api/v1/auth/register', {
    method: 'POST',
    body: JSON.stringify(input),
  })
  writeSession(body.tokens)
  return body
}

export async function login(input: { email: string; password: string }): Promise<User> {
  const { body } = await apiFetch<TokenPair>('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify(input),
  })
  writeSession(body)
  return currentUser()
}

export async function currentUser(): Promise<User> {
  return authedRequest<User>('/api/v1/auth/me')
}

export async function logout(): Promise<void> {
  if (!readSession()) {
    return
  }
  try {
    await authedRequest<void>('/api/v1/auth/logout', { method: 'POST' })
  } catch {
    // A rejected logout still ends the local session; the token expires anyway.
  } finally {
    clearSession()
  }
}

/** Irreversible account deletion: every owned row is removed by cascade. */
export async function deleteAccount(): Promise<void> {
  await authedRequest<void>('/api/v1/users/me', { method: 'DELETE' })
  clearSession()
}
