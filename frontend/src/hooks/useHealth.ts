import { useQuery } from '@tanstack/react-query'
import { ApiError } from '../services/api'
import { fetchHealth } from '../services/health'

export const healthQueryKey = ['health'] as const

export function useHealth() {
  return useQuery({
    queryKey: healthQueryKey,
    queryFn: ({ signal }) => fetchHealth(signal),
    refetchInterval: 30_000,
    retry: 1,
    staleTime: 15_000,
    refetchOnWindowFocus: false,
  })
}

export function describeHealthError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message
  }

  if (error instanceof Error) {
    return error.message
  }

  return 'An unexpected error occurred while checking the API.'
}

export function healthErrorRequestId(error: unknown): string | null {
  return error instanceof ApiError ? error.requestId : null
}
