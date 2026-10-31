/**
 * Resume and analysis history.
 *
 * Deletion is destructive in two different ways — removing a resume also
 * removes every analysis, recommendation and export derived from it — so the
 * confirmation states the consequence in words and needs a second click. No
 * browser dialog: it can be dismissed without reading, and it cannot explain a
 * cascade.
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Badge } from '../components/Badge'
import { EmptyState, ErrorNotice, LoadingState, PageHeader } from '../components/States'
import { deleteAnalysis, listAnalyses } from '../services/analyses'
import { deleteResume, listResumes } from '../services/resumes'

interface DeleteTarget {
  kind: 'resume' | 'analysis'
  id: string
}

// Kept local: Badge's tone union is structural, so no export is needed.
type Tone = 'ok' | 'warn' | 'bad' | 'neutral' | 'info'

function formatDate(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) {
    return iso
  }
  return date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

function analysisTone(status: string): Tone {
  switch (status) {
    case 'completed':
      return 'ok'
    case 'failed':
      return 'bad'
    case 'running':
    case 'queued':
      return 'warn'
    default:
      return 'neutral'
  }
}

function ConfirmDelete({
  label,
  consequence,
  busy,
  onConfirm,
  onCancel,
}: {
  label: string
  consequence: string
  busy: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-rose-400/30 bg-rose-400/5 p-3 sm:max-w-sm">
      <p className="text-xs leading-relaxed text-rose-100">{consequence}</p>
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={onConfirm}
          disabled={busy}
          className="inline-flex items-center rounded-lg border border-rose-400/40 bg-rose-500/20 px-3 py-1.5 text-xs font-semibold text-rose-100 hover:bg-rose-500/30 disabled:opacity-60"
        >
          {busy ? 'Deleting…' : label}
        </button>
        <button type="button" onClick={onCancel} disabled={busy} className="btn-ghost px-3 py-1.5 text-xs">
          Cancel
        </button>
      </div>
    </div>
  )
}

export function HistoryPage() {
  const queryClient = useQueryClient()
  const [target, setTarget] = useState<DeleteTarget | null>(null)
  const [failure, setFailure] = useState<unknown>(null)

  const resumesQuery = useQuery({ queryKey: ['resumes'], queryFn: () => listResumes(50) })
  const analysesQuery = useQuery({ queryKey: ['analyses'], queryFn: () => listAnalyses(50) })

  const resumeDeletion = useMutation({
    mutationFn: (resumeId: string) => deleteResume(resumeId),
    onSuccess: () => {
      setTarget(null)
      setFailure(null)
      void queryClient.invalidateQueries({ queryKey: ['resumes'] })
      // The cascade means the analysis list is no longer accurate either.
      void queryClient.invalidateQueries({ queryKey: ['analyses'] })
    },
    onError: (error: unknown) => {
      setFailure(error)
    },
  })

  const analysisDeletion = useMutation({
    mutationFn: (analysisId: string) => deleteAnalysis(analysisId),
    onSuccess: () => {
      setTarget(null)
      setFailure(null)
      void queryClient.invalidateQueries({ queryKey: ['analyses'] })
    },
    onError: (error: unknown) => {
      setFailure(error)
    },
  })

  const busy = resumeDeletion.isPending || analysisDeletion.isPending
  const resumes = resumesQuery.data?.items ?? []
  const analyses = analysesQuery.data?.items ?? []

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        eyebrow="Your data"
        title="History"
        description="Every document you have uploaded and every analysis computed from it. Deleting here deletes the stored file as well as the record."
        actions={
          <Link to="/app/upload" className="btn-primary">
            New analysis
          </Link>
        }
      />

      {failure ? (
        <ErrorNotice error={failure} title="That deletion did not complete" onRetry={() => setFailure(null)} />
      ) : null}

      <section aria-labelledby="resumes-heading" className="panel p-5 sm:p-6">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="resumes-heading" className="text-lg font-semibold text-ink">
            Resumes
          </h2>
          <p className="text-xs text-muted">
            {resumesQuery.isSuccess ? `${resumes.length} stored` : '—'}
          </p>
        </div>

        <div className="mt-4">
          {resumesQuery.isPending ? (
            <LoadingState label="Loading your resumes…" />
          ) : resumesQuery.isError ? (
            <ErrorNotice error={resumesQuery.error} onRetry={() => void resumesQuery.refetch()} />
          ) : resumes.length === 0 ? (
            <EmptyState
              title="No resumes yet"
              body="Upload a PDF or DOCX and POTENCIA will parse it, score it, and keep the original intact."
              action={
                <Link to="/app/upload" className="btn-primary">
                  Upload a resume
                </Link>
              }
            />
          ) : (
            <ul className="divide-y divide-line/60">
              {resumes.map((resume) => {
                const confirming = target?.kind === 'resume' && target.id === resume.id
                return (
                  <li key={resume.id} className="flex flex-col gap-3 py-4 first:pt-0 last:pb-0">
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                      <div className="min-w-0">
                        <Link
                          to={`/app/resumes/${resume.id}/studio`}
                          className="truncate text-sm font-semibold text-ink hover:text-electric"
                        >
                          {resume.original_filename}
                        </Link>
                        <p className="mt-1 text-xs text-muted">
                          {formatDate(resume.created_at)}
                          {resume.page_count ? ` · ${resume.page_count} page${resume.page_count === 1 ? '' : 's'}` : ''}
                          {resume.extraction ? ` · extraction ${(resume.extraction.confidence * 100).toFixed(0)}%` : ''}
                        </p>
                      </div>

                      <div className="flex flex-wrap items-center gap-2">
                        <Badge tone={resume.status === 'completed' ? 'ok' : resume.status === 'failed' ? 'bad' : 'warn'}>
                          {resume.status}
                        </Badge>
                        <Link to={`/app/resumes/${resume.id}/studio`} className="btn-ghost px-3 py-1.5 text-xs">
                          Open in studio
                        </Link>
                        {!confirming ? (
                          <button
                            type="button"
                            onClick={() => {
                              setFailure(null)
                              setTarget({ kind: 'resume', id: resume.id })
                            }}
                            className="btn-ghost px-3 py-1.5 text-xs text-rose-200"
                          >
                            Delete
                          </button>
                        ) : null}
                      </div>
                    </div>

                    {confirming ? (
                      <ConfirmDelete
                        label="Delete resume and its analyses"
                        consequence="This also deletes every analysis, recommendation, revision and export derived from this resume. It cannot be undone."
                        busy={busy}
                        onConfirm={() => resumeDeletion.mutate(resume.id)}
                        onCancel={() => setTarget(null)}
                      />
                    ) : null}
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </section>

      <section aria-labelledby="analyses-heading" className="panel p-5 sm:p-6">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="analyses-heading" className="text-lg font-semibold text-ink">
            Analyses
          </h2>
          <p className="text-xs text-muted">
            {analysesQuery.isSuccess ? `${analyses.length} computed` : '—'}
          </p>
        </div>

        <div className="mt-4">
          {analysesQuery.isPending ? (
            <LoadingState label="Loading your analyses…" />
          ) : analysesQuery.isError ? (
            <ErrorNotice error={analysesQuery.error} onRetry={() => void analysesQuery.refetch()} />
          ) : analyses.length === 0 ? (
            <EmptyState
              title="No analyses yet"
              body="An analysis scores the resume you uploaded, estimates ATS compatibility, and lists the fixes with the evidence behind each one."
            />
          ) : (
            <ul className="divide-y divide-line/60">
              {analyses.map((analysis) => {
                const confirming = target?.kind === 'analysis' && target.id === analysis.id
                return (
                  <li key={analysis.id} className="flex flex-col gap-3 py-4 first:pt-0 last:pb-0">
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                      <div className="min-w-0">
                        <Link
                          to={`/app/analyses/${analysis.id}`}
                          className="truncate text-sm font-semibold text-ink hover:text-electric"
                        >
                          Analysis {analysis.id.slice(0, 8)}
                        </Link>
                        <p className="mt-1 text-xs text-muted">
                          {formatDate(analysis.created_at)} · methodology v{analysis.methodology_version}
                        </p>
                      </div>

                      <div className="flex flex-wrap items-center gap-2">
                        <Badge tone={analysisTone(analysis.status)}>{analysis.status}</Badge>
                        <Link
                          to={`/app/analyses/${analysis.id}`}
                          className="btn-ghost px-3 py-1.5 text-xs"
                        >
                          View report
                        </Link>
                        {!confirming ? (
                          <button
                            type="button"
                            onClick={() => {
                              setFailure(null)
                              setTarget({ kind: 'analysis', id: analysis.id })
                            }}
                            className="btn-ghost px-3 py-1.5 text-xs text-rose-200"
                          >
                            Delete
                          </button>
                        ) : null}
                      </div>
                    </div>

                    {confirming ? (
                      <ConfirmDelete
                        label="Delete analysis"
                        consequence="This deletes the stored scores, findings, recommendations and exports for this analysis. It cannot be undone."
                        busy={busy}
                        onConfirm={() => analysisDeletion.mutate(analysis.id)}
                        onCancel={() => setTarget(null)}
                      />
                    ) : null}
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </section>
    </div>
  )
}
