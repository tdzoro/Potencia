import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Badge } from '../components/Badge'
import { EmptyState, ErrorNotice, LoadingState, PageHeader } from '../components/States'
import { compareRevisions, createRevision, listRevisions } from '../services/resumes'
import type { EducationEntry, ProjectEntry, ResumeStructure, Revision } from '../types/domain'

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
  const latest = revisions.length > 0 ? revisions[revisions.length - 1] ?? null : null

  // One resume can hold several named versions ("Backend", "Data"). The studio
  // edits one at a time; the newest is the default because it is what exports.
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const current = useMemo(
    () => revisions.find((revision) => revision.id === selectedId) ?? latest,
    [revisions, selectedId, latest],
  )

  const [working, setWorking] = useState<ResumeStructure | null>(null)
  const [baseline, setBaseline] = useState<ResumeStructure | null>(null)
  const [skillsDraft, setSkillsDraft] = useState('')
  // Comma- and line-separated fields are held as raw text while the user types,
  // so a trailing comma is not deleted mid-keystroke.
  const [technologiesDraft, setTechnologiesDraft] = useState<Record<number, string>>({})
  const [detailsDraft, setDetailsDraft] = useState<Record<number, string>>({})
  const [labelDraft, setLabelDraft] = useState('')
  const [compareFrom, setCompareFrom] = useState('')
  const [compareTo, setCompareTo] = useState('')

  useEffect(() => {
    const content = current?.content ?? null
    if (!content) {
      setWorking(null)
      setBaseline(null)
      setSkillsDraft('')
      setTechnologiesDraft({})
      setDetailsDraft({})
      return
    }
    const copy = cloneStructure(content)
    setWorking(copy)
    setBaseline(cloneStructure(content))
    setSkillsDraft(copy.skills.explicit.join(', '))
    setTechnologiesDraft(
      Object.fromEntries(
        copy.projects.map((project, index) => [index, project.technologies.join(', ')]),
      ),
    )
    setDetailsDraft(
      Object.fromEntries(copy.education.map((entry, index) => [index, entry.details.join('\n')])),
    )
  }, [current?.id, current?.content])

  // Default the comparison to first version vs newest, which is the pair a user
  // wants to see after improving a resume.
  useEffect(() => {
    if (revisions.length === 0) {
      return
    }
    if (!compareFrom) {
      setCompareFrom(revisions[0]?.id ?? '')
    }
    if (!compareTo) {
      setCompareTo(revisions[revisions.length - 1]?.id ?? '')
    }
  }, [revisions, compareFrom, compareTo])

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
        content: {
          ...payload,
          projects: payload.projects.map((project, index) => ({
            ...project,
            technologies: splitTechnologies(index),
          })),
          education: payload.education.map((entry, index) => ({
            ...entry,
            details: splitDetails(index),
          })),
        },
        parent_id: current.id,
        label: labelDraft.trim() || null,
        applied_recommendation_ids: [],
      })
    },
    onSuccess: async (revision) => {
      await queryClient.invalidateQueries({ queryKey: ['revisions', resumeId] })
      setSelectedId(revision.id)
      // The comparison should be about the version that was just saved.
      setCompareTo(revision.id)
      setLabelDraft('')
    },
  })

  const comparison = useMutation({
    mutationFn: (input: { from: string; to: string }) =>
      compareRevisions(resumeId, input.from, input.to),
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

    const projectCount = Math.max(baseline.projects.length, working.projects.length)
    for (let projectIndex = 0; projectIndex < projectCount; projectIndex += 1) {
      const baseProject = baseline.projects[projectIndex]
      const workProject = working.projects[projectIndex]
      const name = workProject?.name ?? baseProject?.name ?? `Project ${projectIndex + 1}`

      if ((baseProject?.name ?? '') !== (workProject?.name ?? '')) {
        list.push(`${name} · name`)
      }
      if ((baseProject?.description ?? '') !== (workProject?.description ?? '')) {
        list.push(`${name} · description`)
      }
      if (
        (baseProject?.technologies ?? []).join(', ') !== splitTechnologies(projectIndex).join(', ')
      ) {
        list.push(`${name} · technologies`)
      }

      const baseBullets = baseProject?.bullets ?? []
      const workBullets = workProject?.bullets ?? []
      const bulletCount = Math.max(baseBullets.length, workBullets.length)
      for (let bulletIndex = 0; bulletIndex < bulletCount; bulletIndex += 1) {
        if ((baseBullets[bulletIndex]?.text ?? '') !== (workBullets[bulletIndex]?.text ?? '')) {
          list.push(`${name} · bullet ${bulletIndex + 1}`)
        }
      }
    }

    const educationCount = Math.max(baseline.education.length, working.education.length)
    for (let entryIndex = 0; entryIndex < educationCount; entryIndex += 1) {
      const baseEntry = baseline.education[entryIndex]
      const workEntry = working.education[entryIndex]
      const name = workEntry?.institution ?? baseEntry?.institution ?? `Education ${entryIndex + 1}`

      if ((baseEntry?.institution ?? '') !== (workEntry?.institution ?? '')) {
        list.push(`${name} · institution`)
      }
      if ((baseEntry?.degree ?? '') !== (workEntry?.degree ?? '')) {
        list.push(`${name} · degree`)
      }
      if ((baseEntry?.field ?? '') !== (workEntry?.field ?? '')) {
        list.push(`${name} · field`)
      }
      if ((baseEntry?.details ?? []).join('\n') !== splitDetails(entryIndex).join('\n')) {
        list.push(`${name} · details`)
      }
    }

    return list
  }, [working, baseline, skillsDraft, technologiesDraft, detailsDraft])

  function splitTechnologies(index: number): string[] {
    return (technologiesDraft[index] ?? '')
      .split(',')
      .map((value) => value.trim())
      .filter((value) => value.length > 0)
  }

  function splitDetails(index: number): string[] {
    return (detailsDraft[index] ?? '')
      .split('\n')
      .map((value) => value.trim())
      .filter((value) => value.length > 0)
  }

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

  function updateProject(index: number, patch: Partial<ProjectEntry>): void {
    setWorking((previous) => {
      if (!previous) {
        return previous
      }
      return {
        ...previous,
        projects: previous.projects.map((project, inner) =>
          inner === index ? { ...project, ...patch } : project,
        ),
      }
    })
  }

  function updateProjectBullet(projectIndex: number, bulletIndex: number, text: string): void {
    setWorking((previous) => {
      if (!previous) {
        return previous
      }
      return {
        ...previous,
        projects: previous.projects.map((project, index) => {
          if (index !== projectIndex) {
            return project
          }
          return {
            ...project,
            bullets: project.bullets.map((bullet, inner) =>
              inner === bulletIndex ? { ...bullet, text } : bullet,
            ),
          }
        }),
      }
    })
  }

  function updateEducation(index: number, patch: Partial<EducationEntry>): void {
    setWorking((previous) => {
      if (!previous) {
        return previous
      }
      return {
        ...previous,
        education: previous.education.map((entry, inner) =>
          inner === index ? { ...entry, ...patch } : entry,
        ),
      }
    })
  }

  function resetDraft(): void {
    if (!baseline) {
      return
    }
    const copy = cloneStructure(baseline)
    setWorking(copy)
    setSkillsDraft(copy.skills.explicit.join(', '))
    setTechnologiesDraft(
      Object.fromEntries(
        copy.projects.map((project, index) => [index, project.technologies.join(', ')]),
      ),
    )
    setDetailsDraft(
      Object.fromEntries(copy.education.map((entry, index) => [index, entry.details.join('\n')])),
    )
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
        description="Change your summary, your bullets, your skills, your projects and your education. Saving creates a new revision — the original parse is never overwritten, so you can always walk back."
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

          <section className="panel p-5" aria-labelledby="projects-heading">
            <div className="flex items-center justify-between gap-3">
              <h2 id="projects-heading" className="text-sm font-semibold uppercase tracking-[0.18em] text-muted">
                Projects
              </h2>
              <Badge tone="neutral">{working.projects.length} parsed</Badge>
            </div>

            {working.projects.length === 0 ? (
              <p className="mt-3 text-sm text-muted">
                No projects were parsed from this document. Nothing is invented here — add them to the document
                and upload it again.
              </p>
            ) : (
              <ol className="mt-4 flex flex-col gap-6">
                {working.projects.map((project, projectIndex) => (
                  <li key={`${project.name ?? 'project'}-${projectIndex}`} className="flex flex-col gap-3">
                    <label
                      htmlFor={`project-name-${projectIndex}`}
                      className="flex flex-col gap-1 text-xs text-muted"
                    >
                      Project name
                      <input
                        id={`project-name-${projectIndex}`}
                        type="text"
                        value={project.name ?? ''}
                        onChange={(event) => updateProject(projectIndex, { name: event.target.value })}
                        className="rounded-xl border border-line bg-void/60 px-3 py-2 text-sm text-ink focus:border-electric"
                      />
                    </label>

                    <label
                      htmlFor={`project-description-${projectIndex}`}
                      className="flex flex-col gap-1 text-xs text-muted"
                    >
                      Description
                      <textarea
                        id={`project-description-${projectIndex}`}
                        value={project.description ?? ''}
                        onChange={(event) => updateProject(projectIndex, { description: event.target.value })}
                        rows={2}
                        className="rounded-xl border border-line bg-void/60 px-3 py-2 text-sm leading-relaxed text-ink focus:border-electric"
                      />
                    </label>

                    <label
                      htmlFor={`project-technologies-${projectIndex}`}
                      className="flex flex-col gap-1 text-xs text-muted"
                    >
                      Technologies (comma-separated)
                      <input
                        id={`project-technologies-${projectIndex}`}
                        type="text"
                        value={technologiesDraft[projectIndex] ?? ''}
                        onChange={(event) =>
                          setTechnologiesDraft((previous) => ({
                            ...previous,
                            [projectIndex]: event.target.value,
                          }))
                        }
                        className="rounded-xl border border-line bg-void/60 px-3 py-2 text-sm text-ink focus:border-electric"
                      />
                    </label>

                    {project.bullets.length === 0 ? (
                      <p className="text-xs text-muted">This project has no bullet points in the parsed structure.</p>
                    ) : (
                      <ul className="flex flex-col gap-2">
                        {project.bullets.map((bullet, bulletIndex) => (
                          <li key={`${projectIndex}-${bulletIndex}`}>
                            <label
                              htmlFor={`project-bullet-${projectIndex}-${bulletIndex}`}
                              className="sr-only"
                            >
                              Bullet {bulletIndex + 1} of {project.name ?? 'project'}
                            </label>
                            <textarea
                              id={`project-bullet-${projectIndex}-${bulletIndex}`}
                              value={bullet.text}
                              onChange={(event) =>
                                updateProjectBullet(projectIndex, bulletIndex, event.target.value)
                              }
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

          <section className="panel p-5" aria-labelledby="education-heading">
            <div className="flex items-center justify-between gap-3">
              <h2 id="education-heading" className="text-sm font-semibold uppercase tracking-[0.18em] text-muted">
                Education
              </h2>
              <Badge tone="neutral">{working.education.length} parsed</Badge>
            </div>

            {working.education.length === 0 ? (
              <p className="mt-3 text-sm text-muted">
                No education entries were parsed. A non-standard heading is the usual cause; rename it to
                "Education" in the document and upload it again.
              </p>
            ) : (
              <ol className="mt-4 flex flex-col gap-6">
                {working.education.map((entry, entryIndex) => (
                  <li key={`${entry.institution ?? 'education'}-${entryIndex}`} className="flex flex-col gap-3">
                    <div className="grid gap-3 sm:grid-cols-2">
                      <label
                        htmlFor={`education-institution-${entryIndex}`}
                        className="flex flex-col gap-1 text-xs text-muted"
                      >
                        Institution
                        <input
                          id={`education-institution-${entryIndex}`}
                          type="text"
                          value={entry.institution ?? ''}
                          onChange={(event) => updateEducation(entryIndex, { institution: event.target.value })}
                          className="rounded-xl border border-line bg-void/60 px-3 py-2 text-sm text-ink focus:border-electric"
                        />
                      </label>
                      <label
                        htmlFor={`education-degree-${entryIndex}`}
                        className="flex flex-col gap-1 text-xs text-muted"
                      >
                        Degree
                        <input
                          id={`education-degree-${entryIndex}`}
                          type="text"
                          value={entry.degree ?? ''}
                          onChange={(event) => updateEducation(entryIndex, { degree: event.target.value })}
                          className="rounded-xl border border-line bg-void/60 px-3 py-2 text-sm text-ink focus:border-electric"
                        />
                      </label>
                      <label
                        htmlFor={`education-field-${entryIndex}`}
                        className="flex flex-col gap-1 text-xs text-muted"
                      >
                        Field
                        <input
                          id={`education-field-${entryIndex}`}
                          type="text"
                          value={entry.field ?? ''}
                          onChange={(event) => updateEducation(entryIndex, { field: event.target.value })}
                          className="rounded-xl border border-line bg-void/60 px-3 py-2 text-sm text-ink focus:border-electric"
                        />
                      </label>
                    </div>

                    <label
                      htmlFor={`education-details-${entryIndex}`}
                      className="flex flex-col gap-1 text-xs text-muted"
                    >
                      Detail lines (one per line)
                      <textarea
                        id={`education-details-${entryIndex}`}
                        value={detailsDraft[entryIndex] ?? ''}
                        onChange={(event) =>
                          setDetailsDraft((previous) => ({ ...previous, [entryIndex]: event.target.value }))
                        }
                        rows={2}
                        className="rounded-xl border border-line bg-void/60 px-3 py-2 text-sm leading-relaxed text-ink focus:border-electric"
                      />
                    </label>
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
          <section className="panel p-5" aria-labelledby="version-heading">
            <h2 id="version-heading" className="text-sm font-semibold uppercase tracking-[0.18em] text-muted">
              Version
            </h2>
            <label htmlFor="version-select" className="mt-3 block text-xs text-muted">
              Editing
            </label>
            <select
              id="version-select"
              value={current.id}
              onChange={(event) => setSelectedId(event.target.value)}
              className="mt-1 w-full rounded-xl border border-line bg-void/60 px-3 py-2 text-sm text-ink focus:border-electric"
            >
              {revisions.map((revision, index) => (
                <option key={revision.id} value={revision.id}>
                  v{index}
                  {revision.label ? ` · ${revision.label}` : ''}
                </option>
              ))}
            </select>
            <p className="mt-2 text-[11px] text-muted/80">
              Switching versions loads that version as the working copy. Unsaved edits are discarded.
            </p>
          </section>

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

            <label htmlFor="version-label" className="mt-4 block text-xs text-muted">
              Name this version (optional)
            </label>
            <input
              id="version-label"
              type="text"
              value={labelDraft}
              maxLength={80}
              onChange={(event) => setLabelDraft(event.target.value)}
              className="mt-1 w-full rounded-xl border border-line bg-void/60 px-3 py-2 text-sm text-ink focus:border-electric"
              placeholder="Backend engineer"
            />

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
                    {revision.label ? (
                      <p className="mt-1 text-[11px] font-semibold text-ink">{revision.label}</p>
                    ) : null}
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

          <section className="panel p-5" aria-labelledby="compare-heading">
            <h2 id="compare-heading" className="text-sm font-semibold uppercase tracking-[0.18em] text-muted">
              Compare versions
            </h2>
            <p className="mt-2 text-xs text-muted">
              Two versions, field by field — the check before exporting one for a different role.
            </p>

            <div className="mt-3 grid grid-cols-2 gap-2">
              <label htmlFor="compare-from" className="flex flex-col gap-1 text-[11px] text-muted">
                From
                <select
                  id="compare-from"
                  value={compareFrom}
                  onChange={(event) => setCompareFrom(event.target.value)}
                  className="rounded-lg border border-line bg-void/60 px-2 py-1.5 text-xs text-ink focus:border-electric"
                >
                  {revisions.map((revision, index) => (
                    <option key={revision.id} value={revision.id}>
                      v{index}
                      {revision.label ? ` · ${revision.label}` : ''}
                    </option>
                  ))}
                </select>
              </label>
              <label htmlFor="compare-to" className="flex flex-col gap-1 text-[11px] text-muted">
                To
                <select
                  id="compare-to"
                  value={compareTo}
                  onChange={(event) => setCompareTo(event.target.value)}
                  className="rounded-lg border border-line bg-void/60 px-2 py-1.5 text-xs text-ink focus:border-electric"
                >
                  {revisions.map((revision, index) => (
                    <option key={revision.id} value={revision.id}>
                      v{index}
                      {revision.label ? ` · ${revision.label}` : ''}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <button
              type="button"
              className="btn-ghost mt-3 w-full"
              disabled={!compareFrom || !compareTo || comparison.isPending}
              onClick={() => comparison.mutate({ from: compareFrom, to: compareTo })}
            >
              {comparison.isPending ? 'Comparing…' : 'Compare'}
            </button>

            {comparison.isError ? (
              <div className="mt-3">
                <ErrorNotice error={comparison.error} title="The versions could not be compared" />
              </div>
            ) : null}

            {comparison.data ? (
              comparison.data.changes.length === 0 ? (
                <p className="mt-3 text-xs text-muted" role="status">
                  These versions are identical.
                </p>
              ) : (
                <ul className="mt-3 flex flex-col gap-2">
                  {comparison.data.changes.map((change) => (
                    <li key={change.field} className="rounded-lg border border-line px-3 py-2">
                      <p className="font-mono text-[11px] text-muted">{change.field}</p>
                      <p className="mt-1 text-xs text-rose-200 line-through">{change.before ?? '—'}</p>
                      <p className="text-xs text-emerald-200">{change.after ?? '—'}</p>
                    </li>
                  ))}
                </ul>
              )
            ) : null}
          </section>
        </aside>
      </div>
    </div>
  )
}
