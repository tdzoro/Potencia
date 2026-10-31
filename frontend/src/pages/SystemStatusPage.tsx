import type { ReactNode } from 'react'
import { StatusPill } from '../components/StatusPill'
import type { StatusTone } from '../components/StatusPill'
import {
  describeHealthError,
  healthErrorRequestId,
  useHealth,
} from '../hooks/useHealth'
import { API_BASE_URL } from '../services/api'
import type { HealthSnapshot } from '../types/api'

function formatUptime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) {
    return 'Unknown'
  }

  const total = Math.floor(seconds)
  const days = Math.floor(total / 86_400)
  const hours = Math.floor((total % 86_400) / 3_600)
  const minutes = Math.floor((total % 3_600) / 60)
  const secs = total % 60

  if (days > 0) {
    return `${days}d ${hours}h ${minutes}m`
  }

  if (hours > 0) {
    return `${hours}h ${minutes}m ${secs}s`
  }

  if (minutes > 0) {
    return `${minutes}m ${secs}s`
  }

  return `${secs}s`
}

function formatTimestamp(iso: string): string {
  const parsed = new Date(iso)

  if (Number.isNaN(parsed.getTime())) {
    return 'Unknown'
  }

  return parsed.toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

interface DetailRowProps {
  label: string
  children: ReactNode
}

function DetailRow({ label, children }: DetailRowProps) {
  return (
    <div className="flex flex-col gap-1 border-b border-line/60 py-3 last:border-b-0 sm:flex-row sm:items-center sm:justify-between sm:gap-6">
      <dt className="text-sm text-muted">{label}</dt>
      <dd className="text-sm font-medium text-ink">{children}</dd>
    </div>
  )
}

function HealthDetails({ snapshot }: { snapshot: HealthSnapshot }) {
  const { health, httpStatus, checkedAt } = snapshot
  const tone: StatusTone = health.status === 'ok' ? 'ok' : 'warn'
  const databaseOk = health.dependencies.database === 'ok'

  return (
    <>
      <div className="flex flex-wrap items-center gap-3">
        <StatusPill tone={tone}>
          {health.status === 'ok' ? 'Operational' : 'Degraded'}
        </StatusPill>
        <span className="text-xs text-muted">
          Reported by the API as HTTP {httpStatus}
        </span>
      </div>

      {health.status !== 'ok' ? (
        <p className="mt-4 rounded-lg border border-amber-400/30 bg-amber-400/10 p-3 text-sm text-amber-200">
          The API is reachable but reports a degraded dependency. Analysis requests will fail until
          the database is available again.
        </p>
      ) : null}

      <dl className="mt-6">
        <DetailRow label="Backend version">
          <span className="font-mono text-xs">{health.version}</span>
        </DetailRow>
        <DetailRow label="Environment">
          <span className="font-mono text-xs">{health.environment}</span>
        </DetailRow>
        <DetailRow label="Database dependency">
          <span className={databaseOk ? 'text-emerald-300' : 'text-rose-300'}>
            {health.dependencies.database}
          </span>
        </DetailRow>
        <DetailRow label="Uptime">{formatUptime(health.uptime_seconds)}</DetailRow>
        <DetailRow label="Last checked">{formatTimestamp(checkedAt)}</DetailRow>
        <DetailRow label="API origin">
          <span className="break-all font-mono text-xs">{API_BASE_URL}</span>
        </DetailRow>
      </dl>
    </>
  )
}

export function SystemStatusPage() {
  const healthQuery = useHealth()
  const { data, isPending, isError, error, isFetching, refetch } = healthQuery

  let content: ReactNode

  if (isPending) {
    content = (
      <div className="flex items-center gap-3 py-6" role="status">
        <span
          aria-hidden="true"
          className="h-2 w-2 animate-breathe rounded-full bg-electric"
        />
        <p className="text-sm text-muted">Contacting the POTENCIA API…</p>
      </div>
    )
  } else if (isError) {
    const requestId = healthErrorRequestId(error)

    content = (
      <div className="py-2">
        <div className="flex flex-wrap items-center gap-3">
          <StatusPill tone="error">Unreachable</StatusPill>
        </div>
        <p className="mt-4 text-sm leading-relaxed text-muted">{describeHealthError(error)}</p>
        <p className="mt-3 text-sm leading-relaxed text-muted">
          Start the backend and refresh. The client is asking{' '}
          <span className="break-all font-mono text-xs text-ink">{API_BASE_URL}/health</span>.
        </p>
        {requestId ? (
          <p className="mt-3 font-mono text-xs text-muted">Request ID: {requestId}</p>
        ) : null}
      </div>
    )
  } else if (data) {
    content = <HealthDetails snapshot={data} />
  } else {
    content = (
      <p className="py-6 text-sm text-muted">
        The health check finished without returning a usable payload.
      </p>
    )
  }

  return (
    <div className="max-w-3xl">
      <p className="label">Diagnostics</p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
        System status
      </h1>
      <p className="mt-4 max-w-2xl text-base leading-relaxed text-muted">
        This page reads the backend health endpoint directly. It is the proof that the interface and
        the API are wired together — no cached values, no simulated responses.
      </p>

      <section aria-labelledby="health-panel-heading" className="panel mt-8 p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="health-panel-heading" className="text-sm font-semibold text-ink">
            API health
          </h2>
          <button
            type="button"
            onClick={() => {
              void refetch()
            }}
            disabled={isFetching}
            className="btn-ghost"
          >
            {isFetching ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>

        <div aria-live="polite" className="mt-5">
          {content}
        </div>
      </section>

      <p className="mt-6 text-xs leading-relaxed text-muted">
        Health is polled every 30 seconds. A 503 response from the API is displayed as a degraded
        state rather than treated as a client failure.
      </p>
    </div>
  )
}
