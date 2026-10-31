import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { Badge, severityTone, statusTone } from '../components/Badge'
import { ScoreBars, ScoreDial } from '../components/ScoreVisuals'
import { EmptyState, ErrorNotice, LoadingState, PageHeader } from '../components/States'
import { getReport } from '../services/analyses'
import type { AnalysisDetail, Evidence, Finding, Severity } from '../types/domain'

const SEVERITY_ORDER: Severity[] = ['critical', 'high', 'medium', 'low', 'info']

const SEVERITY_LABEL: Record<Severity, string> = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
  info: 'Info',
}

function formatDate(iso: string | null): string {
  if (!iso) {
    return '—'
  }
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) {
    return iso
  }
  return date.toLocaleString(undefined, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function EvidenceList({ evidence }: { evidence: Evidence[] }) {
  if (evidence.length === 0) {
    return null
  }

  return (
    <ul className="mt-3 flex flex-col gap-2">
      {evidence.map((item, index) => (
        <li
          key={`${item.section}-${index}`}
          className="rounded-lg border border-line/70 bg-void/50 px-3 py-2"
        >
          <p className="text-[11px] uppercase tracking-[0.14em] text-muted/70">
            {item.section}
            {item.page !== null ? ` · page ${item.page}` : ''}
          </p>
          <p className="mt-1 border-l-2 border-electric/50 pl-3 text-sm italic leading-relaxed text-ink/90">
            {item.text}
          </p>
        </li>
      ))}
    </ul>
  )
}

function FindingCard({ finding }: { finding: Finding }) {
  return (
    <li className="panel p-5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={severityTone(finding.severity)}>{SEVERITY_LABEL[finding.severity]}</Badge>
        <span className="font-mono text-[11px] text-muted/70">{finding.criterion}</span>
        <span className="ml-auto font-mono text-xs text-rose-300">
          {finding.score_impact !== null ? `−${finding.score_impact.toFixed(1)} points` : 'no deduction'}
        </span>
      </div>

      <h3 className="mt-3 text-base font-semibold text-ink">{finding.title}</h3>
      <p className="mt-2 text-sm leading-relaxed text-muted">{finding.explanation}</p>

      <EvidenceList evidence={finding.evidence} />

      <p className="mt-3 text-sm leading-relaxed text-ink/90">
        <span className="label mr-2 align-middle">Fix</span>
        {finding.remediation}
      </p>
    </li>
  )
}

function AtsSection({ analysis }: { analysis: AnalysisDetail }) {
  const ats = analysis.ats
  if (!ats) {
    return null
  }

  const pass = ats.summary['pass'] ?? 0
  const warn = ats.summary['warn'] ?? 0
  const fail = ats.summary['fail'] ?? 0

  return (
    <section aria-labelledby="ats-heading" className="panel p-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="label">ATS compatibility</p>
          <h2 id="ats-heading" className="mt-2 text-xl font-semibold text-ink">
            {ats.estimate.toFixed(1)}
            <span className="ml-1 text-sm font-normal text-muted">/ 100 estimate</span>
          </h2>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="ok">{pass} pass</Badge>
          <Badge tone="warn">{warn} warn</Badge>
          <Badge tone="bad">{fail} fail</Badge>
        </div>
      </div>

      <p className="mt-4 text-xs leading-relaxed text-muted">{ats.disclaimer}</p>

      <ul className="mt-5 flex flex-col gap-3">
        {ats.checks.map((check) => (
          <li key={check.id} className="rounded-xl border border-line/70 bg-void/40 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={statusTone(check.status)}>{check.status}</Badge>
              <p className="text-sm font-semibold text-ink">{check.label}</p>
            </div>
            <p className="mt-2 text-sm leading-relaxed text-muted">{check.explanation}</p>
            <p className="mt-2 text-sm leading-relaxed text-ink/90">{check.remediation}</p>
            <EvidenceList evidence={check.evidence} />
          </li>
        ))}
      </ul>
    </section>
  )
}

export function ReportPage() {
  const { analysisId } = useParams<{ analysisId: string }>()

  const query = useQuery({
    queryKey: ['analysis', analysisId],
    queryFn: () => getReport(analysisId ?? ''),
    enabled: Boolean(analysisId),
  })

  if (!analysisId) {
    return (
      <EmptyState
        title="No analysis selected"
        body="Open a report from your history to see its breakdown."
        action={
          <Link to="/app/history" className="btn-ghost">
            Go to history
          </Link>
        }
      />
    )
  }

  if (query.isPending) {
    return <LoadingState label="Loading the report…" />
  }

  if (query.isError) {
    return <ErrorNotice error={query.error} onRetry={() => void query.refetch()} />
  }

  const analysis = query.data
  const scores = analysis.scores

  if (!scores || analysis.status !== 'completed') {
    return (
      <div className="flex flex-col gap-4">
        <PageHeader eyebrow="Analysis" title="This analysis is not ready" />
        <div className="panel p-6">
          <div className="flex items-center gap-3">
            <Badge tone={analysis.status === 'failed' ? 'bad' : 'warn'}>{analysis.status}</Badge>
            <p className="text-sm text-muted">
              {analysis.status === 'failed'
                ? 'The analysis could not be completed.'
                : 'The report appears as soon as the analysis finishes.'}
            </p>
          </div>
          {analysis.failure ? (
            <pre className="mt-4 overflow-x-auto rounded-lg border border-line/70 bg-void/60 p-3 text-xs text-muted">
              {JSON.stringify(analysis.failure, null, 2)}
            </pre>
          ) : null}
        </div>
      </div>
    )
  }

  const grouped = SEVERITY_ORDER.map((severity) => ({
    severity,
    findings: analysis.findings.filter((finding) => finding.severity === severity),
  })).filter((group) => group.findings.length > 0)

  const deduction = analysis.findings.reduce((total, finding) => total + (finding.score_impact ?? 0), 0)

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        eyebrow="Analysis report"
        title="Resume intelligence report"
        description={`Scored ${formatDate(analysis.completed_at ?? analysis.created_at)} · scoring methodology v${analysis.methodology_version}`}
        actions={
          <>
            <Link to={`/app/analyses/${analysis.id}/recommendations`} className="btn-primary">
              Recommendations
            </Link>
            <Link to={`/app/analyses/${analysis.id}/match`} className="btn-ghost">
              Job match
            </Link>
            <Link to={`/app/analyses/${analysis.id}/export`} className="btn-ghost">
              Export
            </Link>
          </>
        }
      />

      <section aria-labelledby="score-heading" className="panel p-6">
        <h2 id="score-heading" className="label">
          Overall score
        </h2>
        <div className="mt-4 grid gap-8 lg:grid-cols-[auto,1fr] lg:items-center">
          <div className="flex flex-col items-center gap-3">
            <ScoreDial score={scores.overall} band={scores.band} />
            <p className="text-center text-xs text-muted">
              {scores.applicable_weight} of 100 weight applicable
              <br />
              <span className="text-muted/70">
                {analysis.findings.length} finding{analysis.findings.length === 1 ? '' : 's'} ·{' '}
                {deduction.toFixed(1)} points deducted
              </span>
            </p>
          </div>
          <ScoreBars scores={scores} />
        </div>
      </section>

      <AtsSection analysis={analysis} />

      <section aria-labelledby="findings-heading">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <h2 id="findings-heading" className="text-xl font-semibold text-ink">
            Findings and evidence
          </h2>
          <p className="text-xs text-muted">
            Every deduction cites the text that caused it. Nothing here is inferred from a model.
          </p>
        </div>

        {grouped.length === 0 ? (
          <div className="panel mt-4 p-6">
            <p className="text-sm text-ink">No findings were raised.</p>
            <p className="mt-2 text-sm text-muted">
              That is a valid outcome: the resume met every applicable criterion. It is not a
              prediction of interview success.
            </p>
          </div>
        ) : (
          <div className="mt-4 flex flex-col gap-6">
            {grouped.map((group) => (
              <div key={group.severity}>
                <div className="flex items-center gap-2">
                  <Badge tone={severityTone(group.severity)}>{SEVERITY_LABEL[group.severity]}</Badge>
                  <span className="text-xs text-muted">
                    {group.findings.length} finding{group.findings.length === 1 ? '' : 's'}
                  </span>
                </div>
                <ul className="mt-3 flex flex-col gap-3">
                  {group.findings.map((finding) => (
                    <FindingCard key={finding.id} finding={finding} />
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section aria-labelledby="strengths-heading" className="panel p-6">
          <h2 id="strengths-heading" className="text-lg font-semibold text-ink">
            Strengths
          </h2>
          {analysis.strengths.length === 0 ? (
            <p className="mt-3 text-sm text-muted">
              No strengths were recorded for this document.
            </p>
          ) : (
            <ul className="mt-4 flex flex-col gap-4">
              {analysis.strengths.map((strength, index) => (
                <li key={index}>
                  <p className="text-sm text-ink">{strength.text}</p>
                  <EvidenceList evidence={strength.evidence} />
                </li>
              ))}
            </ul>
          )}
        </section>

        <section aria-labelledby="actions-heading" className="panel p-6">
          <h2 id="actions-heading" className="text-lg font-semibold text-ink">
            Priority actions
          </h2>
          {analysis.priority_actions.length === 0 ? (
            <p className="mt-3 text-sm text-muted">Nothing is pending. The report is clean.</p>
          ) : (
            <ol className="mt-4 flex flex-col gap-3">
              {analysis.priority_actions.map((action, index) => (
                <li key={index} className="flex gap-3 text-sm leading-relaxed text-ink/90">
                  <span className="mt-0.5 font-mono text-xs text-electric">
                    {String(index + 1).padStart(2, '0')}
                  </span>
                  <span>{action}</span>
                </li>
              ))}
            </ol>
          )}
        </section>
      </div>

      <p className="rounded-xl border border-line/70 bg-void/40 p-4 text-xs leading-relaxed text-muted">
        The six category weights are product-design hypotheses, not empirically validated industry
        standards; they will change when calibrated against a reviewed dataset, and stored reports
        keep the methodology version they were scored with. The same document scored twice produces
        the same number, because every rule is deterministic.
      </p>
    </div>
  )
}
