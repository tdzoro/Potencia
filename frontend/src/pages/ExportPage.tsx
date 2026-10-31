import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Badge } from '../components/Badge'
import { EmptyState, ErrorNotice, LoadingState, PageHeader } from '../components/States'
import { createExport, getReport } from '../services/analyses'
import { cn } from '../utils/cn'
import type { ExportRecord } from '../types/domain'

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

function ExportCard({ record }: { record: ExportRecord }) {
  const statusTone = record.status === 'completed' ? 'ok' : record.status === 'failed' ? 'bad' : 'warn'
  const failureMessage =
    typeof record.failure?.['message'] === 'string' ? record.failure['message'] : null

  return (
    <li className="rounded-xl border border-line/70 bg-surface/60 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-ink">
            {record.kind === 'analysis_report' ? 'Analysis report' : 'Improved resume'} ·{' '}
            {record.format.toUpperCase()}
          </p>
          <p className="mt-1 text-xs text-muted">
            {formatBytes(record.size_bytes)} · link expires {formatTimestamp(record.expires_at)}
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
  const [records, setRecords] = useState<ExportRecord[]>([])

  const report = useQuery({
    queryKey: ['report', analysisId],
    queryFn: () => getReport(analysisId as string),
    enabled: Boolean(analysisId),
  })

  const request = useMutation({
    mutationFn: (input: { kind: 'analysis_report' | 'improved_resume'; format: 'pdf' | 'docx' }) =>
      createExport({ analysis_id: analysisId as string, kind: input.kind, format: input.format }),
    onSuccess: (record) => {
      setRecords((current) => [record, ...current])
    },
  })

  if (!analysisId) {
    return <EmptyState title="No analysis selected" body="Open a resume report to export it." />
  }

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
              Your newest approved revision, in a single-column layout. Change nothing and it exports
              the original parse untouched.
            </p>
          </div>

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
            onClick={() => request.mutate({ kind: 'improved_resume', format: resumeFormat })}
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
          Generated in this session
        </h2>

        {records.length === 0 ? (
          <EmptyState
            title="Nothing generated yet"
            body="Choose a format above. Each file is rendered on demand from this analysis, then served through a signed link."
          />
        ) : (
          <ul className="flex flex-col gap-2">
            {records.map((record) => (
              <ExportCard key={record.id} record={record} />
            ))}
          </ul>
        )}

        <p className="text-xs leading-relaxed text-muted/80">
          Download links are signed, bound to your account and expire after 15 minutes. The generated
          file itself is removed after 24 hours, so download it while the link is live.
        </p>
      </section>
    </div>
  )
}
