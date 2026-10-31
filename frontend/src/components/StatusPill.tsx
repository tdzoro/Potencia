import type { ReactNode } from 'react'
import { cn } from '../utils/cn'

export type StatusTone = 'ok' | 'warn' | 'error' | 'idle'

const toneStyles: Record<StatusTone, string> = {
  ok: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300',
  warn: 'border-amber-400/30 bg-amber-400/10 text-amber-300',
  error: 'border-rose-400/30 bg-rose-400/10 text-rose-300',
  idle: 'border-line bg-surface/80 text-muted',
}

const dotStyles: Record<StatusTone, string> = {
  ok: 'bg-emerald-400',
  warn: 'bg-amber-400',
  error: 'bg-rose-400',
  idle: 'bg-muted',
}

interface StatusPillProps {
  tone: StatusTone
  children: ReactNode
}

export function StatusPill({ tone, children }: StatusPillProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-2 rounded-full border px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em]',
        toneStyles[tone],
      )}
    >
      <span aria-hidden="true" className={cn('h-1.5 w-1.5 rounded-full', dotStyles[tone])} />
      {children}
    </span>
  )
}
