import { cn } from '../utils/cn'
import type { ReactNode } from 'react'

type Tone = 'ok' | 'warn' | 'bad' | 'neutral' | 'info'

const tones: Record<Tone, string> = {
  ok: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300',
  warn: 'border-amber-400/30 bg-amber-400/10 text-amber-300',
  bad: 'border-rose-400/30 bg-rose-400/10 text-rose-300',
  neutral: 'border-line bg-surface/80 text-muted',
  info: 'border-electric/40 bg-electric/10 text-electric',
}

export function Badge({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.12em]',
        tones[tone],
      )}
    >
      {children}
    </span>
  )
}

export function severityTone(severity: string): Tone {
  switch (severity) {
    case 'critical':
    case 'high':
      return 'bad'
    case 'medium':
      return 'warn'
    case 'low':
    case 'info':
      return 'neutral'
    default:
      return 'neutral'
  }
}

export function statusTone(status: string): Tone {
  switch (status) {
    case 'pass':
    case 'matched':
      return 'ok'
    case 'warn':
    case 'partial':
    case 'weakly_demonstrated':
      return 'warn'
    case 'fail':
    case 'absent':
      return 'bad'
    default:
      return 'neutral'
  }
}
