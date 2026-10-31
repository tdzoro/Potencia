import { SCORE_CATEGORY_LABELS } from '../types/domain'
import type { ScoreBand, ScoreBundle, ScoreCategory } from '../types/domain'
import { cn } from '../utils/cn'

const bandColor: Record<ScoreBand, string> = {
  critical: '#f87171',
  developing: '#fbbf24',
  competent: '#38bdf8',
  strong: '#34d399',
  exceptional: '#8b5cf6',
}

/** A single-number gauge. The arc is drawn from the score itself, never faked. */
export function ScoreDial({
  score,
  band,
  caption,
  size = 168,
}: {
  score: number
  band: ScoreBand
  caption?: string
  size?: number
}) {
  const clamped = Math.max(0, Math.min(100, score))
  const radius = size / 2 - 12
  const circumference = 2 * Math.PI * radius
  const dash = (clamped / 100) * circumference

  return (
    <div className="flex flex-col items-center gap-2">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${clamped.toFixed(1)} out of 100`}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(255,255,255,0.08)"
          strokeWidth={10}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={bandColor[band]}
          strokeWidth={10}
          strokeLinecap="round"
          strokeDasharray={`${dash} ${circumference - dash}`}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
        <text
          x="50%"
          y="47%"
          textAnchor="middle"
          dominantBaseline="middle"
          fill="#e8eaf6"
          fontSize={size * 0.22}
          fontWeight={600}
        >
          {clamped.toFixed(1)}
        </text>
        <text
          x="50%"
          y="62%"
          textAnchor="middle"
          dominantBaseline="middle"
          fill="#9aa3c7"
          fontSize={size * 0.075}
          letterSpacing="1.5"
        >
          {band.toUpperCase()}
        </text>
      </svg>
      {caption ? <p className="text-xs text-muted">{caption}</p> : null}
    </div>
  )
}

/** Weighted category bars — contribution is shown, not just the raw value. */
export function ScoreBars({ scores }: { scores: ScoreBundle }) {
  const entries = Object.entries(scores.components) as Array<
    [ScoreCategory, ScoreBundle['components'][ScoreCategory]]
  >

  return (
    <ul className="flex flex-col gap-3">
      {entries.map(([category, component]) => {
        const contribution = (component.value * component.weight) / 100
        return (
          <li key={category} className="flex flex-col gap-1.5">
            <div className="flex items-baseline justify-between gap-3 text-sm">
              <span className="text-ink">{SCORE_CATEGORY_LABELS[category] ?? category}</span>
              <span className="font-mono text-xs text-muted">
                {component.value.toFixed(1)}
                <span className="text-muted/60"> × {component.weight}%</span>
                <span className="ml-2 text-ink">{contribution.toFixed(1)}</span>
              </span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/5">
              <div
                className="h-full rounded-full bg-brand-gradient"
                style={{ width: `${Math.max(0, Math.min(100, component.value))}%` }}
              />
            </div>
            <p className="text-[11px] uppercase tracking-[0.14em] text-muted/70">
              confidence {component.confidence}
            </p>
          </li>
        )
      })}
    </ul>
  )
}

export function MiniMeter({ value, label, tone = 'electric' }: { value: number; label: string; tone?: 'electric' | 'emerald' | 'amber' | 'rose' }) {
  const color = {
    electric: 'bg-electric',
    emerald: 'bg-emerald-400',
    amber: 'bg-amber-400',
    rose: 'bg-rose-400',
  }[tone]

  return (
    <div className="flex items-center gap-3">
      <span className="w-40 shrink-0 text-xs text-muted">{label}</span>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/5">
        <div className={cn('h-full rounded-full', color)} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
      </div>
      <span className="w-10 shrink-0 text-right font-mono text-xs text-ink">{value.toFixed(0)}</span>
    </div>
  )
}
