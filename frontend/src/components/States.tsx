import type { ReactNode } from 'react'
import { ApiError } from '../services/api'

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 py-10 text-sm text-muted" role="status" aria-live="polite">
      <span className="h-2 w-2 animate-breathe rounded-full bg-electric" aria-hidden="true" />
      {label}
    </div>
  )
}

export function ErrorNotice({
  error,
  onRetry,
  title = 'Something went wrong',
}: {
  error: unknown
  onRetry?: () => void
  title?: string
}) {
  const api = error instanceof ApiError ? error : null
  const message = api?.message ?? (error instanceof Error ? error.message : 'An unexpected error occurred.')

  return (
    <div className="panel border-rose-400/30 p-5" role="alert">
      <p className="text-sm font-semibold text-rose-200">{title}</p>
      <p className="mt-2 text-sm text-muted">{message}</p>
      {api?.requestId ? (
        <p className="mt-2 font-mono text-[11px] text-muted/70">request {api.requestId}</p>
      ) : null}
      {onRetry ? (
        <button type="button" onClick={onRetry} className="btn-ghost mt-4">
          Try again
        </button>
      ) : null}
    </div>
  )
}

export function EmptyState({
  title,
  body,
  action,
}: {
  title: string
  body: string
  action?: ReactNode
}) {
  return (
    <div className="panel flex flex-col items-center gap-3 px-6 py-12 text-center">
      <p className="text-base font-semibold text-ink">{title}</p>
      <p className="max-w-md text-sm text-muted">{body}</p>
      {action}
    </div>
  )
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string
  title: string
  description?: string
  actions?: ReactNode
}) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="max-w-2xl">
        {eyebrow ? <p className="label">{eyebrow}</p> : null}
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-ink sm:text-3xl">{title}</h1>
        {description ? <p className="mt-2 text-sm leading-relaxed text-muted">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  )
}
