import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Badge } from '../components/Badge'
import { EmptyState, ErrorNotice, LoadingState, PageHeader } from '../components/States'
import { createExport, getReport, listExports } from '../services/analyses'
import { listRevisions } from '../services/resumes'
import { cn } from '../utils/cn'
import type { ExportRecord, Revision } from '../types/domain'

function formatBytes(bytes: number | null): string {
  if (bytes === null || bytes <= 0) {
    return '—'
  }
  if (bytes < 1024) {
    return `${bytes} B`
  }
  return `${(bytes / 1024).toFixed(1)} KB`
}

function formatTimestamp(value: string | null): string {
  if (!value) {
    return '—'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return '—'
  }
  return date.toLocaleString()
}

/** "v2 · Platform", or the truth when that version no longer exists. */
function versionLabel(record: ExportRecord, versions: Revision[]): string | null {
  if (!record.revision_id) {
    return null
  }
  const index = versions.findIndex((revision) => revision.id === record.revision_id)
  if (index < 0) {
    return 'version unavailable'
  }
  const label = versions[index]?.label
  return `v${index}${label ? ` · ${label}` : ''}`
}

function ExportCard({ record, versions }: { record: ExportRecord; versions: Revision[] }) {
  const statusTone = record.status === 'completed' ? 'ok' : record.status === 'failed' ? 'bad' : 'warn'
  const failureMessage =
    typeof record.failure?.['message'] === 'string' ? record.failure['message'] : null
  const exported = versionLabel(record, versions)

  return (
    <li className="rounded-xl border border-line/70 bg-surface/60 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-ink">
            {record.kind === 'analysis_report' ? 'Analysis report' : 'Improved resume'} ·{' '}
            {record.format.toUpperCase()}
            {exported ? <span className="text-muted"> · {exported}</span> : null}
          </p>
          <p className="mt-1 text-xs text-muted">
            {formatBytes(record.size_bytes)} · expires {formatTimestamp(record.expires_at)}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Badge tone={statusTone}>{record.status}</Badge>
          {record.status === 'completed' && record.download_url ? (
            <a
              href={record.download_url}
              target="_blank"
              rel="noreferrer"
              className="btn-primary px-3 py-1.5 text-xs"
            >
              Download
            </a>
          ) : null}
        </div>
      </div>
      {record.status === 'failed' ? (
        <p className="mt-2 text-xs text-rose-200">
          {failureMessage ?? 'The file could not be generated. Try again.'}
        </p>
      ) : null}
      {record.status !== 'completed' && record.status !== 'failed' ? (
        <p className="mt-2 text-xs text-muted">Preparing the file…</p>
      ) : null}
    </li>
  )
}

export function ExportPage() {
  const { analysisId } = useParams<{ analysisId: string }>()
  const [resumeFormat, setResumeFormat] = useState<'pdf' | 'docx'>('pdf')
  const [revisionChoice, setRevisionChoice] = useState('')
  const queryClient = useQueryClient()

  const report = useQuery({
    queryKey: ['report', analysisId],
    queryFn: () => getReport(analysisId as string),
    enabled: Boolean(analysisId),
  })

  // Shared cache key with the studio: a version saved there is selectable here
  // without a reload, and the label in the history is the label it was given.
  const resumeId = report.data?.resume_id
  const revisions = useQuery({
    queryKey: ['revisions', resumeId],
    queryFn: () => listRevisions(resumeId as string),
    enabled: Boolean(resumeId),
  })
  const versions: Revision[] = revisions.data ?? []

  // Export history is persisted, so a reload keeps the files that already exist
  // instead of pretending they were never generated.
  const history = useQuery({
    queryKey: ['exports', analysisId],
    queryFn: () => listExports(analysisId as string),
    enabled: Boolean(analysisId),
  })

  const request = useMutation({
    mutationFn: (input: {
      kind: 'analysis_report' | 'improved_resume'
      format: 'pdf' | 'docx'
      revision_id?: string | null
    }) =>
      createExport({
        analysis_id: analysisId as string,
        kind: input.kind,
        format: input.format,
        revision_id: input.revision_id ?? null,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['exports', analysisId] })
    },
  })

  if (!analysisId) {
    return <EmptyState title="No analysis selected" body="Open a resume report to export it." />
  }

  const records = history.data ?? []

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        eyebrow="Export"
        title="Take the result with you"
        description="The report carries the scores, the ATS checks and the findings that produced them. The improved resume is the version you approved, laid out so it still survives parsing."
        actions={
          <Link to={`/app/analyses/${analysisId}`} className="btn-ghost">
            Back to report
          </Link>
        }
      />

      {report.status === 'pending' ? <LoadingState label="Loading the analysis…" /> : null}
      {report.status === 'error' ? (
        <ErrorNotice error={report.error} onRetry={() => void report.refetch()} />
      ) : null}
      {request.error ? <ErrorNotice error={request.error} title="The export could not be created" /> : null}

      <div className="grid gap-6 md:grid-cols-2">
        <section className="panel flex flex-col gap-4 p-6" aria-labelledby="export-report">
          <div>
            <h2 id="export-report" className="text-base font-semibold text-ink">
              Analysis report
            </h2>
            <p className="mt-1 text-sm text-muted">
              Every score, its weighting, the ATS checks and the findings with their evidence, in one
              paginated PDF.
            </p>
          </div>
          <button
            type="button"
            className="btn-primary self-start"
            disabled={request.isPending}
            onClick={() => request.mutate({ kind: 'analysis_report', format: 'pdf' })}
          >
            {request.isPending ? 'Generating…' : 'Generate report PDF'}
          </button>
          <p className="text-[11px] text-muted/70">PDF only. A report is a fixed record of one analysis.</p>
        </section>

        <section className="panel flex flex-col gap-4 p-6" aria-labelledby="export-resume">
          <div>
            <h2 id="export-resume" className="text-base font-semibold text-ink">
              Improved resume
            </h2>
            <p className="mt-1 text-sm text-muted">
              The version you choose — newest by default — in a single-column layout. Change nothing and
              it exports the original parse untouched.
            </p>
          </div>

          <label htmlFor="export-version" className="flex flex-col gap-1 text-xs text-muted">
            Resume version
            <select
              id="export-version"
              value={revisionChoice}
              onChange={(event) => setRevisionChoice(event.target.value)}
              className="rounded-xl border border-line bg-void/60 px-3 py-2 text-sm text-ink focus:border-electric"
            >
              <option value="">Newest version</option>
              {versions.map((revision, index) => (
                <option key={revision.id} value={revision.id}>
                  v{index}
                  {revision.label ? ` · ${revision.label}` : ''}
                </option>
              ))}
            </select>
          </label>

          <fieldset className="flex items-center gap-2">
            <legend className="sr-only">Resume format</legend>
            {(['pdf', 'docx'] as const).map((format) => (
              <button
                key={format}
                type="button"
                aria-pressed={resumeFormat === format}
                onClick={() => setResumeFormat(format)}
                className={cn(
                  'rounded-lg border px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.12em]',
                  resumeFormat === format
                    ? 'border-electric/60 bg-electric/15 text-ink'
                    : 'border-line bg-surface/60 text-muted hover:text-ink',
                )}
              >
                {format}
              </button>
            ))}
          </fieldset>

          <button
            type="button"
            className="btn-primary self-start"
            disabled={request.isPending}
            onClick={() =>
              request.mutate({
                kind: 'improved_resume',
                format: resumeFormat,
                revision_id: revisionChoice || null,
              })
            }
          >
            {request.isPending ? 'Generating…' : `Generate resume ${resumeFormat.toUpperCase()}`}
          </button>
          <p className="text-[11px] text-muted/70">
            DOCX stays editable. PDF keeps the layout fixed.
          </p>
        </section>
      </div>

      <section aria-labelledby="export-history" className="flex flex-col gap-3">
        <h2 id="export-history" className="text-base font-semibold text-ink">
          Generated for this analysis
        </h2>

        {history.status === 'pending' ? <LoadingState label="Loading exports…" /> : null}
        {history.status === 'error' ? (
          <ErrorNotice error={history.error} onRetry={() => void history.refetch()} />
        ) : null}

        {history.status === 'success' && records.length === 0 ? (
          <EmptyState
            title="Nothing generated yet"
            body="Choose a format above. Each file is rendered on demand from this analysis, then served through a signed link."
          />
        ) : null}

        {records.length > 0 ? (
          <ul className="flex flex-col gap-2">
            {records.map((record) => (
              <ExportCard key={record.id} record={record} versions={versions} />
            ))}
          </ul>
        ) : null}

        <p className="text-xs leading-relaxed text-muted/80">
          Download links are signed, bound to your account and expire after 15 minutes. The generated
          file itself is removed after 24 hours, so download it while the link is live.
        </p>
      </section>
    </div>
  )
}
