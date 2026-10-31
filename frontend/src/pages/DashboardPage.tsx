import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Badge } from '../components/Badge'
import { MiniMeter, ScoreDial } from '../components/ScoreVisuals'
import { EmptyState, ErrorNotice, LoadingState, PageHeader } from '../components/States'
import { useAuth } from '../context/AuthContext'
import { getReport, listAnalyses } from '../services/analyses'
import { listResumes } from '../services/resumes'
import { SCORE_CATEGORY_LABELS } from '../types/domain'
import type { Analysis, ScoreCategory } from '../types/domain'

const CATEGORY_ORDER: ScoreCategory[] = [
  'content_quality',
  'experience',
  'skills',
  'structure',
  'ats_compatibility',
  'language_readability',
]

const STATUS_TONE: Record<Analysis['status'], 'ok' | 'warn' | 'bad' | 'neutral'> = {
  completed: 'ok',
  queued: 'neutral',
  running: 'warn',
  failed: 'bad',
}

function formatDate(iso: string): string {
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

function metersFrom(report: { scores: { components: Record<ScoreCategory, { value: number }> } | null }) {
  const components = report.scores?.components
  if (!components) {
    return []
  }
  return CATEGORY_ORDER.flatMap((category) => {
    const component = components[category]
    if (!component) {
      return []
    }
    return [{ category, label: SCORE_CATEGORY_LABELS[category], value: component.value }]
  })
}

export function DashboardPage() {
  const { user } = useAuth()

  const analysesQuery = useQuery({
    queryKey: ['analyses', 8],
    queryFn: () => listAnalyses(8),
  })
  const resumesQuery = useQuery({
    queryKey: ['resumes', 20],
    queryFn: () => listResumes(20),
  })

  const newestCompleted = analysesQuery.data?.items.find((item) => item.status === 'completed')
  const reportQuery = useQuery({
    queryKey: ['report', newestCompleted?.id],
    queryFn: () => getReport(newestCompleted ? newestCompleted.id : ''),
    enabled: Boolean(newestCompleted?.id),
  })

  const greeting = user?.display_name ?? user?.email ?? 'there'
  const resumeCount = resumesQuery.data?.items.length ?? 0
  const recent = analysesQuery.data?.items.slice(0, 5) ?? []
  const report = reportQuery.data
  const atsSummary = report?.ats?.summary ?? {}

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        eyebrow="Dashboard"
        title={`Welcome back, ${greeting}`}
        description="Every number here was computed from your document by deterministic rules. Open a report to see the evidence behind each deduction."
        actions={
          <Link to="/app/upload" className="btn-primary">
            Analyse a resume
          </Link>
        }
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="panel p-5">
          <p className="label">Resumes stored</p>
          <p className="mt-2 font-mono text-2xl text-ink">{resumeCount}</p>
          <p className="mt-1 text-xs text-muted">Documents you have uploaded.</p>
        </div>
        <div className="panel p-5">
          <p className="label">Analyses run</p>
          <p className="mt-2 font-mono text-2xl text-ink">{analysesQuery.data?.items.length ?? 0}</p>
          <p className="mt-1 text-xs text-muted">Each one is kept with its methodology version.</p>
        </div>
        <div className="panel p-5">
          <p className="label">Latest score</p>
          <p className="mt-2 font-mono text-2xl text-ink">
            {typeof report?.scores?.overall === 'number' ? report.scores.overall.toFixed(1) : '—'}
          </p>
          <p className="mt-1 text-xs text-muted">
            {report?.scores ? `Band: ${report.scores.band}` : 'Run an analysis to see this.'}
          </p>
        </div>
      </div>

      <section aria-labelledby="latest-heading" className="flex flex-col gap-4">
        <h2 id="latest-heading" className="text-lg font-semibold text-ink">
          Latest analysis
        </h2>

        {analysesQuery.isPending ? <LoadingState label="Loading your analyses…" /> : null}

        {analysesQuery.isError ? (
          <ErrorNotice
            error={analysesQuery.error}
            onRetry={() => void analysesQuery.refetch()}
            title="Could not load your analyses"
          />
        ) : null}

        {!analysesQuery.isPending && !analysesQuery.isError && !newestCompleted ? (
          <EmptyState
            title="No analysis yet"
            body="Upload a PDF or DOCX resume and POTENCIA will extract its structure, score it against explicit criteria, and show you exactly which lines cost you points."
            action={
              <Link to="/app/upload" className="btn-primary">
                Upload your first resume
              </Link>
            }
          />
        ) : null}

        {newestCompleted ? (
          reportQuery.isPending ? (
            <LoadingState label="Loading the report…" />
          ) : reportQuery.isError ? (
            <ErrorNotice
              error={reportQuery.error}
              onRetry={() => void reportQuery.refetch()}
              title="Could not load the latest report"
            />
          ) : report?.scores ? (
            <div className="grid gap-4 lg:grid-cols-3">
              <div className="panel flex flex-col items-center justify-center gap-4 p-6">
                <ScoreDial
                  score={report.scores.overall}
                  band={report.scores.band}
                  caption={`Methodology v${report.scores.methodology_version}`}
                />
                <div className="flex flex-wrap items-center justify-center gap-2">
                  <Badge tone="info">{report.scores.applicable_weight} weight applicable</Badge>
                  {typeof report.ats?.estimate === 'number' ? (
                    <Badge tone="neutral">ATS estimate {report.ats.estimate.toFixed(1)}</Badge>
                  ) : null}
                </div>
                <Link to={`/app/analyses/${report.id}`} className="btn-ghost w-full justify-center">
                  Open full report
                </Link>
              </div>

              <div className="panel p-6">
                <p className="label">Category breakdown</p>
                <div className="mt-4 flex flex-col gap-3">
                  {metersFrom(report).map((meter) => (
                    <MiniMeter
                      key={meter.category}
                      label={meter.label}
                      value={meter.value}
                      tone={
                        meter.value >= 75 ? 'emerald' : meter.value >= 50 ? 'electric' : 'amber'
                      }
                    />
                  ))}
                </div>
              </div>

              <div className="panel flex flex-col gap-5 p-6">
                <div>
                  <p className="label">ATS compatibility</p>
                  <div className="mt-3 flex items-center gap-4 text-sm">
                    <span className="font-mono text-2xl text-ink">
                      {typeof report.ats?.estimate === 'number' ? report.ats.estimate.toFixed(1) : '—'}
                    </span>
                    <div className="flex flex-wrap gap-2">
                      <Badge tone="ok">{atsSummary.pass ?? 0} pass</Badge>
                      <Badge tone="warn">{atsSummary.warn ?? 0} warn</Badge>
                      <Badge tone="bad">{atsSummary.fail ?? 0} fail</Badge>
                    </div>
                  </div>
                  <p className="mt-2 text-xs text-muted">
                    A compatibility estimate, not a prediction of any employer&apos;s screening outcome.
                  </p>
                </div>

                <div>
                  <p className="label">Priority actions</p>
                  {report.priority_actions.length > 0 ? (
                    <ol className="mt-3 flex list-decimal flex-col gap-2 pl-4 text-sm text-muted">
                      {report.priority_actions.slice(0, 3).map((action) => (
                        <li key={action}>{action}</li>
                      ))}
                    </ol>
                  ) : (
                    <p className="mt-2 text-sm text-muted">
                      No critical actions — the report found nothing that must be fixed before
                      sending this resume.
                    </p>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <ErrorNotice
              error={new Error('The stored report has no scores.')}
              onRetry={() => void reportQuery.refetch()}
            />
          )
        ) : null}
      </section>

      {recent.length > 0 ? (
        <section aria-labelledby="recent-heading" className="flex flex-col gap-3">
          <h2 id="recent-heading" className="text-lg font-semibold text-ink">
            Recent analyses
          </h2>
          <div className="panel overflow-hidden">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-line/70 text-xs uppercase tracking-[0.14em] text-muted">
                  <th scope="col" className="px-4 py-3 font-semibold">
                    Run
                  </th>
                  <th scope="col" className="px-4 py-3 font-semibold">
                    Status
                  </th>
                  <th scope="col" className="px-4 py-3 font-semibold">
                    Created
                  </th>
                  <th scope="col" className="px-4 py-3 font-semibold">
                    Report
                  </th>
                </tr>
              </thead>
              <tbody>
                {recent.map((analysis) => (
                  <tr key={analysis.id} className="border-b border-line/40 last:border-0">
                    <td className="px-4 py-3 font-mono text-xs text-muted">{analysis.id.slice(0, 8)}</td>
                    <td className="px-4 py-3">
                      <Badge tone={STATUS_TONE[analysis.status]}>{analysis.status}</Badge>
                    </td>
                    <td className="px-4 py-3 text-xs text-muted">{formatDate(analysis.created_at)}</td>
                    <td className="px-4 py-3">
                      {analysis.status === 'completed' ? (
                        <Link
                          to={`/app/analyses/${analysis.id}`}
                          className="text-sm font-semibold text-electric hover:underline"
                        >
                          Open
                        </Link>
                      ) : (
                        <span className="text-xs text-muted">Unavailable</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </div>
  )
}
