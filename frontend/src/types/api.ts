export type HealthStatus = 'ok' | 'degraded'

export interface HealthDependencies {
  database: string
}

export interface HealthResponse {
  status: HealthStatus
  version: string
  environment: string
  dependencies: HealthDependencies
  uptime_seconds: number
}

export interface HealthSnapshot {
  health: HealthResponse
  httpStatus: number
  checkedAt: string
}

export interface ApiErrorDetail {
  field: string
  issue: string
  meta?: Record<string, unknown>
}

export interface ApiErrorBody {
  error: {
    code: string
    message: string
    details?: ApiErrorDetail[]
    request_id?: string
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

export function isHealthResponse(value: unknown): value is HealthResponse {
  if (!isRecord(value)) {
    return false
  }

  const dependencies = value.dependencies
  if (!isRecord(dependencies)) {
    return false
  }

  const status = value.status

  return (
    (status === 'ok' || status === 'degraded') &&
    typeof value.version === 'string' &&
    typeof value.environment === 'string' &&
    typeof dependencies.database === 'string' &&
    typeof value.uptime_seconds === 'number'
  )
}

export function isApiErrorBody(value: unknown): value is ApiErrorBody {
  if (!isRecord(value)) {
    return false
  }

  const error = value.error
  if (!isRecord(error)) {
    return false
  }

  return typeof error.code === 'string' && typeof error.message === 'string'
}
