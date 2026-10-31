import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Badge } from '../components/Badge'
import { EmptyState, ErrorNotice, LoadingState, PageHeader } from '../components/States'
import { createRevision, listRevisions } from '../services/resumes'
import type { ResumeStructure, Revision } from '../types/domain'

function cloneStructure(structure: ResumeStructure): ResumeStructure {
  return JSON.parse(JSON.stringify(structure)) as ResumeStructure
}

function formatTimestamp(iso: string): string {
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

export function StudioPage() {
  const { resumeId = '' } = useParams<{ resumeId: string }>()
  const queryClient = useQueryClient()

  const revisionsQuery = useQuery({
    queryKey: ['revisions', resumeId],
    queryFn: () => listRevisions(resumeId),
    enabled: resumeId.length > 0,
  })

  const revisions: Revision[] = revisionsQuery.data ?? []
  const current = useMemo(() => {
    if (revisions.length === 0) {
      return null
    }
    return revisions[revisions.length - 1] ?? null
  }, [revisions])

  const [working, setWorking] = useState<ResumeStructure | null>(null)
  const [baseline, setBaseline] = useState<ResumeStructure | null>(null)
  const [skillsDraft, setSkillsDraft] = useState('')

  useEffect(() => {
    const content = current?.content ?? null
    if (!content) {
      setWorking(null)
      setBaseline(null)
      setSkillsDraft('')
      return
    }
    const copy = cloneStructure(content)
    setWorking(copy)
    setBaseline(cloneStructure(content))
    setSkillsDraft(copy.skills.explicit.join(', '))
  }, [current?.id, current?.content])

  const save = useMutation({
    mutationFn: async () => {
      if (!working || !current) {
        throw new Error('There is nothing to save.')
      }
      const payload: ResumeStructure = {
        ...working,
        skills: {
          ...working.skills,
          explicit: skillsDraft
            .split(',')
            .map((value) => value.trim())
            .filter((value) => value.length > 0),
        },
      }
      return createRevision(resumeId, {
        content: payload,
        parent_id: current.id,
        applied_recommendation_ids: [],
      })
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['revisions', resumeId] })
    },
  })

  const changes = useMemo(() => {
    if (!working || !baseline) {
      return [] as string[]
    }
    const list: string[] = []

    if ((baseline.summary.text ?? '') !== (working.summary.text ?? '')) {
      list.push('Professional summary')
    }

    const roleCount = Math.max(baseline.experience.length, working.experience.length)
    for (let roleIndex = 0; roleIndex < roleCount; roleIndex += 1) {
      const baseRole = baseline.experience[roleIndex]
      const workRole = working.experience[roleIndex]
      const baseBullets = baseRole?.bullets ?? []
      const workBullets = workRole?.bullets ?? []
      const bulletCount = Math.max(baseBullets.length, workBullets.length)
      const roleLabel = workRole?.title ?? baseRole?.title ?? workRole?.organisation ?? `Role ${roleIndex + 1}`

      for (let bulletIndex = 0; bulletIndex < bulletCount; bulletIndex += 1) {
        if ((baseBullets[bulletIndex]?.text ?? '') !== (workBullets[bulletIndex]?.text ?? '')) {
          list.push(`${roleLabel} · bullet ${bulletIndex + 1}`)
        }
      }
    }

    if (baseline.skills.explicit.join(', ') !== skillsDraft.split(',').map((v) => v.trim()).filter(Boolean).join(', ')) {
      list.push('Skills list')
    }

    return list
  }, [working, baseline, skillsDraft])

  function updateSummary(text: string): void {
    setWorking((previous) => (previous ? { ...previous, summary: { ...previous.summary, text } } : previous))
  }

  function updateBullet(roleIndex: number, bulletIndex: number, text: string): void {
    setWorking((previous) => {
      if (!previous) {
        return previous
      }
      const experience = previous.experience.map((role, index) => {
        if (index !== roleIndex) {
          return role
        }
        return {
          ...role,
          bullets: role.bullets.map((bullet, inner) => (inner === bulletIndex ? { ...bullet, text } : bullet)),
        }
      })
      return { ...previous, experience }
    })
  }

  function resetDraft(): void {
    if (!baseline) {
      return
    }
    const copy = cloneStructure(baseline)
    setWorking(copy)
    setSkillsDraft(copy.skills.explicit.join(', '))
    save.reset()
  }

  if (revisionsQuery.isPending) {
    return <LoadingState label="Opening the revision history…" />
  }

  if (revisionsQuery.isError) {
    return (
      <ErrorNotice
        error={revisionsQuery.error}
        title="The revision history could not be loaded"
        onRetry={() => void revisionsQuery.refetch()}
      />
    )
  }

  if (revisions.length === 0 || !current?.content || !working) {
    return (
      <EmptyState
        title="This resume has no revisions"
        body="A resume is stored with revision 0 — the untouched parse — the moment it is uploaded. Its absence means the document never produced a usable structure, so there is nothing to edit here."
        action={
          <Link to="/app/upload" className="btn-primary">
            Upload a resume
          </Link>
        }
      />
    )
  }

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        eyebrow="Resume improvement studio"
        title="Edit what you can prove"
        description="Change your summary, your bullet wording and your skills list. Saving creates a new revision — the original parse is never overwritten, so you can always walk back."
        actions={
          <Link to="/app/history" className="btn-ghost">
            Resume history
          </Link>
        }
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="flex flex-col gap-6">
          <section className="panel p-5" aria-labelledby="summary-heading">
            <div className="flex items-center justify-between gap-3">
              <h2 id="summary-heading" className="text-sm font-semibold uppercase tracking-[0.18em] text-muted">
                Professional summary
              </h2>
              {working.summary.present ? <Badge tone="ok">present</Badge> : <Badge tone="warn">not detected</Badge>}
            </div>
            <label htmlFor="summary-text" className="sr-only">
              Professional summary text
            </label>
            <textarea
              id="summary-text"
              value={working.summary.text ?? ''}
              onChange={(event) => updateSummary(event.target.value)}
              rows={4}
              className="mt-3 w-full rounded-xl border border-line bg-void/60 px-3 py-2 text-sm leading-relaxed text-ink focus:border-electric"
              placeholder="Write a summary that states the role you want and the result that proves you can do it."
            />
            <p className="mt-2 text-xs text-muted">
              Editing the text does not change whether a summary was detected in the original document.
            </p>
          </section>

          <section className="panel p-5" aria-labelledby="experience-heading">
            <div className="flex items-center justify-between gap-3">
              <h2 id="experience-heading" className="text-sm font-semibold uppercase tracking-[0.18em] text-muted">
                Experience bullets
              </h2>
              <Badge tone="neutral">{working.bullet_count} bullets parsed</Badge>
            </div>

            {working.experience.length === 0 ? (
              <p className="mt-3 text-sm text-muted">
                No experience entries were parsed from this resume, so there are no bullets to edit.
              </p>
            ) : (
              <ol className="mt-4 flex flex-col gap-6">
                {working.experience.map((role, roleIndex) => (
                  <li key={`${role.title ?? 'role'}-${roleIndex}`} className="flex flex-col gap-3">
                    <div>
                      <p className="text-sm font-semibold text-ink">{role.title ?? 'Untitled role'}</p>
                      <p className="text-xs text-muted">
                        {[role.organisation, role.start, role.end].filter(Boolean).join(' · ') || 'No dates parsed'}
                      </p>
                    </div>

                    {role.bullets.length === 0 ? (
                      <p className="text-xs text-muted">This role has no bullet points in the parsed structure.</p>
                    ) : (
                      <ul className="flex flex-col gap-2">
                        {role.bullets.map((bullet, bulletIndex) => (
                          <li key={`${roleIndex}-${bulletIndex}`}>
                            <label htmlFor={`bullet-${roleIndex}-${bulletIndex}`} className="sr-only">
                              Bullet {bulletIndex + 1} of {role.title ?? 'role'}
                            </label>
                            <textarea
                              id={`bullet-${roleIndex}-${bulletIndex}`}
                              value={bullet.text}
                              onChange={(event) => updateBullet(roleIndex, bulletIndex, event.target.value)}
                              rows={2}
                              className="w-full rounded-xl border border-line bg-void/60 px-3 py-2 text-sm leading-relaxed text-ink focus:border-electric"
                            />
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </section>

          <section className="panel p-5" aria-labelledby="skills-heading">
            <h2 id="skills-heading" className="text-sm font-semibold uppercase tracking-[0.18em] text-muted">
              Skills
            </h2>
            <label htmlFor="skills-text" className="mt-3 block text-xs text-muted">
              Comma-separated. Remove anything you cannot defend in an interview.
            </label>
            <input
              id="skills-text"
              type="text"
              value={skillsDraft}
              onChange={(event) => setSkillsDraft(event.target.value)}
              className="mt-2 w-full rounded-xl border border-line bg-void/60 px-3 py-2 text-sm text-ink focus:border-electric"
              placeholder="Python, PostgreSQL, Docker"
            />
            {working.skills.inferred.length > 0 ? (
              <div className="mt-3">
                <p className="text-xs text-muted">
                  Inferred from your prose, not edited here: {working.skills.inferred.map((skill) => skill.name).join(', ')}
                </p>
              </div>
            ) : null}
          </section>
        </div>

        <aside className="flex flex-col gap-4">
          <section className="panel p-5" aria-labelledby="save-heading">
            <h2 id="save-heading" className="text-sm font-semibold uppercase tracking-[0.18em] text-muted">
              Save as a new revision
            </h2>

            <p className="mt-3 text-xs text-muted">
              Current revision <span className="font-mono text-ink">{current.id.slice(0, 8)}</span>
            </p>

            {changes.length === 0 ? (
              <p className="mt-3 text-sm text-muted">No changes yet.</p>
            ) : (
              <>
                <p className="mt-3 text-sm text-ink">
                  {changes.length} field{changes.length === 1 ? '' : 's'} changed
                </p>
                <ul className="mt-2 flex flex-col gap-1">
                  {changes.map((change) => (
                    <li key={change} className="text-xs text-muted">
                      <span aria-hidden="true">· </span>
                      {change}
                    </li>
                  ))}
                </ul>
              </>
            )}

            <div className="mt-4 flex flex-col gap-2">
              <button
                type="button"
                className="btn-primary"
                disabled={changes.length === 0 || save.isPending}
                onClick={() => save.mutate()}
              >
                {save.isPending ? 'Saving…' : 'Save as new revision'}
              </button>
              <button
                type="button"
                className="btn-ghost"
                disabled={changes.length === 0 || save.isPending}
                onClick={resetDraft}
              >
                Discard changes
              </button>
            </div>

            <p className="mt-3 text-xs text-muted">
              The original parse stays intact. Word and bullet counts are not recalculated here — run a new
              analysis to re-score the edited resume.
            </p>

            {save.isError ? (
              <div className="mt-3">
                <ErrorNotice error={save.error} title="The revision was not saved" />
              </div>
            ) : null}

            {save.isSuccess ? (
              <p className="mt-3 text-xs text-emerald-300" role="status">
                Saved. The new revision is now the working copy.
              </p>
            ) : null}
          </section>

          <section className="panel p-5" aria-labelledby="history-heading">
            <h2 id="history-heading" className="text-sm font-semibold uppercase tracking-[0.18em] text-muted">
              Revision history
            </h2>
            <ol className="mt-3 flex flex-col gap-2">
              {revisions.map((revision, index) => {
                const isCurrent = revision.id === current.id
                return (
                  <li
                    key={revision.id}
                    className={
                      isCurrent
                        ? 'rounded-lg border border-electric/40 bg-electric/10 px-3 py-2'
                        : 'rounded-lg border border-line px-3 py-2'
                    }
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-[11px] text-ink">v{index}</span>
                      {isCurrent ? <Badge tone="info">current</Badge> : null}
                    </div>
                    <p className="mt-1 text-[11px] text-muted">{formatTimestamp(revision.created_at)}</p>
                    {revision.parent_id ? (
                      <p className="text-[11px] text-muted/70">
                        parent {revision.parent_id.slice(0, 8)}
                      </p>
                    ) : (
                      <p className="text-[11px] text-muted/70">original parse</p>
                    )}
                  </li>
                )
              })}
            </ol>
          </section>
        </aside>
      </div>
    </div>
  )
}
