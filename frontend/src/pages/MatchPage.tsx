import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Badge, statusTone } from '../components/Badge'
import { MiniMeter } from '../components/ScoreVisuals'
import { EmptyState, ErrorNotice, LoadingState, PageHeader } from '../components/States'
import { createJob, createMatch, deleteJob, getReport, listJobs } from '../services/analyses'
import type { Job, JobMatchResult, Match, SkillMatch } from '../types/domain'

function SkillRow({ skill }: { skill: SkillMatch }) {
  return (
    <li className="flex flex-col gap-1 border-b border-line/60 py-3 last:border-0">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-ink">{skill.name}</span>
        <Badge tone={statusTone(skill.status)}>{skill.status.replace(/_/g, ' ')}</Badge>
      </div>
      <p className="text-xs text-muted">{skill.note}</p>
      {skill.evidence.length > 0 ? (
        <ul className="mt-1 flex flex-col gap-1">
          {skill.evidence.map((line, index) => (
            <li
              key={`${skill.name}-${index}`}
              className="border-l border-line pl-3 font-mono text-[11px] leading-relaxed text-muted/80"
            >
              {line}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-[11px] text-muted/60">No supporting line in the resume.</p>
      )}
    </li>
  )
}

function ResultPanel({ match, jobTitle }: { match: Match; jobTitle: string | null }) {
  const result: JobMatchResult | null = match.result

  if (match.status === 'failed') {
    const message = typeof match.failure?.['message'] === 'string' ? match.failure['message'] : null
    return (
      <div className="panel border-rose-400/30 p-5" role="alert">
        <p className="text-sm font-semibold text-rose-200">Matching failed</p>
        <p className="mt-2 text-sm text-muted">{message ?? 'The matcher could not read this job description.'}</p>
      </div>
    )
  }

  if (!result) {
    return <LoadingState label="Matching…" />
  }

  const { requirements, gaps, summary } = result

  return (
    <div className="flex flex-col gap-6">
      <div className="panel p-6">
        <p className="label">Match estimate</p>
        <p className="mt-2 text-3xl font-semibold text-ink">{result.estimate.toFixed(1)}</p>
        <p className="mt-1 text-xs text-muted">
          {jobTitle ?? 'Saved job'} · methodology v{result.methodology_version}
        </p>
        <div className="mt-4">
          <MiniMeter value={result.estimate} label="Resume to requirement" tone="electric" />
        </div>
        <dl className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {Object.entries(summary).map(([key, value]) => (
            <div key={key} className="rounded-xl border border-line/70 bg-surface/60 p-3">
              <dt className="text-[11px] uppercase tracking-[0.14em] text-muted">{key.replace(/_/g, ' ')}</dt>
              <dd className="mt-1 font-mono text-sm text-ink">{value}</dd>
            </div>
          ))}
        </dl>
      </div>

      <section className="panel p-6" aria-labelledby="required-skills">
        <h2 id="required-skills" className="text-base font-semibold text-ink">
          Required skills
        </h2>
        {requirements.required_skills.length === 0 ? (
          <p className="mt-2 text-sm text-muted">This description names no specific required skills.</p>
        ) : (
          <ul className="mt-2">
            {requirements.required_skills.map((skill) => (
              <SkillRow key={`required-${skill.name}`} skill={skill} />
            ))}
          </ul>
        )}
      </section>

      <section className="panel p-6" aria-labelledby="preferred-skills">
        <h2 id="preferred-skills" className="text-base font-semibold text-ink">
          Preferred skills
        </h2>
        {requirements.preferred_skills.length === 0 ? (
          <p className="mt-2 text-sm text-muted">This description names no preferred skills.</p>
        ) : (
          <ul className="mt-2">
            {requirements.preferred_skills.map((skill) => (
              <SkillRow key={`preferred-${skill.name}`} skill={skill} />
            ))}
          </ul>
        )}
      </section>

      <section className="panel p-6" aria-labelledby="other-requirements">
        <h2 id="other-requirements" className="text-base font-semibold text-ink">
          Experience and education
        </h2>
        <ul className="mt-3 flex flex-col gap-3 text-sm">
          <li className="flex flex-wrap items-center gap-2">
            <span className="text-muted">Years required</span>
            <span className="font-mono text-ink">
              {requirements.experience_years.required ?? 'not stated'}
            </span>
            <span className="text-muted">demonstrated</span>
            <span className="font-mono text-ink">
              {requirements.experience_years.demonstrated ?? 'not determinable'}
            </span>
            <Badge tone={statusTone(requirements.experience_years.status)}>
              {requirements.experience_years.status.replace(/_/g, ' ')}
            </Badge>
          </li>
          <li className="flex flex-wrap items-center gap-2">
            <span className="text-muted">Degree required</span>
            <span className="text-ink">{requirements.education.required ?? 'not stated'}</span>
            <Badge tone={statusTone(requirements.education.status)}>
              {requirements.education.status.replace(/_/g, ' ')}
            </Badge>
          </li>
        </ul>
      </section>

      {requirements.responsibilities.length > 0 ? (
        <section className="panel p-6" aria-labelledby="responsibilities">
          <h2 id="responsibilities" className="text-base font-semibold text-ink">
            Responsibilities
          </h2>
          <ul className="mt-3 flex flex-col gap-2">
            {requirements.responsibilities.map((item, index) => (
              <li key={`responsibility-${index}`} className="flex items-start gap-3 text-sm">
                <Badge tone={statusTone(item.status)}>{item.status.replace(/_/g, ' ')}</Badge>
                <span className="text-muted">{item.text}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="panel p-6" aria-labelledby="gaps">
        <h2 id="gaps" className="text-base font-semibold text-ink">
          Gaps
        </h2>
        {gaps.length === 0 ? (
          <p className="mt-2 text-sm text-muted">No requirement is missing from this resume.</p>
        ) : (
          <ul className="mt-3 flex flex-col gap-3">
            {gaps.map((gap) => (
              <li key={gap.name} className="rounded-xl border border-line/70 bg-surface/60 p-4">
                <p className="text-sm font-medium text-ink">{gap.name}</p>
                <p className="mt-1 text-sm text-muted">{gap.advice}</p>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-4 text-xs leading-relaxed text-muted/80">
          A missing skill is reported, never added on your behalf. POTENCIA will not write a claim
          into your resume that you have not made yourself.
        </p>
      </section>
    </div>
  )
}

export function MatchPage() {
  const { analysisId } = useParams<{ analysisId: string }>()
  const queryClient = useQueryClient()

  const [title, setTitle] = useState('')
  const [company, setCompany] = useState('')
  const [description, setDescription] = useState('')
  const [activeMatch, setActiveMatch] = useState<{ match: Match; jobTitle: string | null } | null>(null)

  const report = useQuery({
    queryKey: ['report', analysisId],
    queryFn: () => getReport(analysisId as string),
    enabled: Boolean(analysisId),
  })

  const jobs = useQuery({ queryKey: ['jobs'], queryFn: listJobs })

  const matchJob = useMutation({
    mutationFn: async (job: Job) => {
      const resumeId = report.data?.resume_id
      if (!resumeId) {
        throw new Error('The analysis has not loaded yet.')
      }
      const match = await createMatch(resumeId, job.id)
      return { match, jobTitle: job.title ?? job.company }
    },
    onSuccess: (data) => {
      setActiveMatch(data)
    },
  })

  const addJob = useMutation({
    mutationFn: async () => {
      const job = await createJob({
        title: title.trim() || undefined,
        company: company.trim() || undefined,
        description: description.trim(),
      })
      const resumeId = report.data?.resume_id
      if (!resumeId) {
        throw new Error('The analysis has not loaded yet.')
      }
      const match = await createMatch(resumeId, job.id)
      return { match, jobTitle: job.title ?? job.company }
    },
    onSuccess: async (data) => {
      setActiveMatch(data)
      setTitle('')
      setCompany('')
      setDescription('')
      await queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })

  const removeJob = useMutation({
    mutationFn: (jobId: string) => deleteJob(jobId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })

  if (!analysisId) {
    return <EmptyState title="No analysis selected" body="Open a resume report and start a match from there." />
  }

  const trimmedDescription = description.trim()
  const canSubmit = trimmedDescription.length >= 20 && !addJob.isPending && report.status === 'success'
  // Creation errors are shown beside the form; re-match and delete errors are not.
  const actionError = matchJob.error ?? removeJob.error

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        eyebrow="Job matching"
        title="How this resume reads against one specific job"
        description="Requirements are extracted from the description, normalised, and compared against evidence in the resume. The number is aggregated from those comparisons — not from a model's impression."
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

      {actionError ? (
        <ErrorNotice error={actionError} title="The last action did not complete" />
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
        <div className="flex flex-col gap-6">
          <form
            className="panel flex flex-col gap-3 p-6"
            onSubmit={(event) => {
              event.preventDefault()
              if (canSubmit) {
                addJob.mutate()
              }
            }}
          >
            <h2 className="text-base font-semibold text-ink">Paste a job description</h2>
            <label className="flex flex-col gap-1 text-xs text-muted">
              Role title (optional)
              <input
                type="text"
                value={title}
                maxLength={200}
                onChange={(event) => setTitle(event.target.value)}
                className="rounded-lg border border-line bg-void/60 px-3 py-2 text-sm text-ink"
                placeholder="Senior Backend Engineer"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-muted">
              Company (optional)
              <input
                type="text"
                value={company}
                maxLength={200}
                onChange={(event) => setCompany(event.target.value)}
                className="rounded-lg border border-line bg-void/60 px-3 py-2 text-sm text-ink"
                placeholder="Acme Payments"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-muted">
              Description
              <textarea
                required
                rows={8}
                maxLength={40_000}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                className="rounded-lg border border-line bg-void/60 px-3 py-2 font-mono text-xs leading-relaxed text-ink"
                placeholder="Paste the full posting here…"
              />
            </label>
            <p className="text-[11px] text-muted/70">
              {trimmedDescription.length} characters · at least 20 required
            </p>
            <button type="submit" className="btn-primary" disabled={!canSubmit}>
              {addJob.isPending ? 'Matching…' : 'Match this job'}
            </button>
            {addJob.error ? <ErrorNotice error={addJob.error} title="Could not match this job" /> : null}
          </form>

          <section className="panel p-6" aria-labelledby="saved-jobs">
            <h2 id="saved-jobs" className="text-base font-semibold text-ink">
              Saved descriptions
            </h2>
            {jobs.status === 'pending' ? <LoadingState label="Loading saved jobs…" /> : null}
            {jobs.status === 'success' && jobs.data.length === 0 ? (
              <p className="mt-2 text-sm text-muted">
                Nothing saved yet. A description is stored so you can re-match it later.
              </p>
            ) : null}
            {jobs.status === 'success' && jobs.data.length > 0 ? (
              <ul className="mt-3 flex flex-col gap-2">
                {jobs.data.map((job) => (
                  <li
                    key={job.id}
                    className="flex items-start justify-between gap-3 rounded-xl border border-line/70 bg-surface/60 p-3"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm text-ink">{job.title ?? 'Untitled role'}</p>
                      <p className="text-xs text-muted">{job.company ?? 'No company given'}</p>
                      {job.requirements ? (
                        <p className="mt-1 text-[11px] text-muted/70">
                          {job.requirements.required_skills.length} required ·{' '}
                          {job.requirements.preferred_skills.length} preferred
                        </p>
                      ) : null}
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-1">
                      <button
                        type="button"
                        className="btn-ghost px-3 py-1 text-xs"
                        disabled={matchJob.isPending}
                        onClick={() => matchJob.mutate(job)}
                      >
                        Match
                      </button>
                      <button
                        type="button"
                        className="text-[11px] text-muted hover:text-rose-300"
                        disabled={removeJob.isPending}
                        onClick={() => removeJob.mutate(job.id)}
                      >
                        Delete
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            ) : null}
          </section>
        </div>

        <div>
          {activeMatch ? (
            <ResultPanel match={activeMatch.match} jobTitle={activeMatch.jobTitle} />
          ) : (
            <EmptyState
              title="No match yet"
              body="Paste a description on the left, or pick a saved one, to see matched, partially matched and absent requirements side by side."
            />
          )}
        </div>
      </div>
    </div>
  )
}
