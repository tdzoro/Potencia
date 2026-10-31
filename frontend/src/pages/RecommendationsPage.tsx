import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Badge } from '../components/Badge'
import { EmptyState, ErrorNotice, LoadingState, PageHeader } from '../components/States'
import { decideRecommendation, getReport, listRecommendations } from '../services/analyses'
import type { Recommendation } from '../types/domain'

const priorityTone = (priority: Recommendation['priority']) =>
  priority === 'high' ? 'bad' : priority === 'medium' ? 'warn' : 'neutral'

const stateTone = (state: Recommendation['state']) =>
  state === 'accepted' ? 'ok' : state === 'rejected' ? 'bad' : state === 'edited' ? 'info' : 'neutral'

const CATEGORY_LABELS: Record<Recommendation['category'], string> = {
  summary: 'Summary',
  experience_bullet: 'Experience bullet',
  project_description: 'Project',
  achievement: 'Achievement',
  skills_organisation: 'Skills',
  grammar: 'Grammar',
  clarity: 'Clarity',
  relevance: 'Relevance',
  keyword_placement: 'Keywords',
  formatting: 'Formatting',
}

interface ActionVars {
  recommendationId: string
  decision: 'accept' | 'reject' | 'edit'
  editedText?: string
}

export function RecommendationsPage() {
  const { analysisId = '' } = useParams<{ analysisId: string }>()
  const queryClient = useQueryClient()

  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [filter, setFilter] = useState<'all' | 'pending' | 'decided'>('all')

  const reportQuery = useQuery({
    queryKey: ['report', analysisId],
    queryFn: () => getReport(analysisId),
    enabled: analysisId.length > 0,
  })

  const recommendationsQuery = useQuery({
    queryKey: ['recommendations', analysisId],
    queryFn: () => listRecommendations(analysisId),
    enabled: analysisId.length > 0,
  })

  const decision = useMutation({
    mutationFn: ({ recommendationId, decision: choice, editedText }: ActionVars) =>
      decideRecommendation(recommendationId, choice, editedText),
    onSuccess: async () => {
      setEditingId(null)
      setDraft('')
      await queryClient.invalidateQueries({ queryKey: ['recommendations', analysisId] })
    },
  })

  const items = recommendationsQuery.data ?? []
  const resumeId = reportQuery.data?.resume_id ?? null

  const counts = useMemo(() => {
    const base = { pending: 0, accepted: 0, rejected: 0, edited: 0 }
    for (const item of items) {
      base[item.state] += 1
    }
    return base
  }, [items])

  const visible = useMemo(() => {
    if (filter === 'pending') {
      return items.filter((item) => item.state === 'pending')
    }
    if (filter === 'decided') {
      return items.filter((item) => item.state !== 'pending')
    }
    return items
  }, [items, filter])

  const grouped = useMemo(() => {
    const order: Recommendation['priority'][] = ['high', 'medium', 'low']
    return order
      .map((priority) => ({ priority, rows: visible.filter((item) => item.priority === priority) }))
      .filter((group) => group.rows.length > 0)
  }, [visible])

  if (recommendationsQuery.isPending) {
    return <LoadingState label="Reviewing your evidence…" />
  }

  if (recommendationsQuery.isError) {
    return (
      <ErrorNotice
        error={recommendationsQuery.error}
        title="Recommendations could not be loaded"
        onRetry={() => void recommendationsQuery.refetch()}
      />
    )
  }

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        eyebrow="Improvement studio"
        title="Recommendations"
        description="Each card cites the line it came from. Accept what is right, reject what is not, and edit anything that needs your own wording — nothing is ever applied without your approval."
        actions={
          resumeId ? (
            <Link to={`/app/resumes/${resumeId}/studio`} className="btn-primary">
              Open the studio
            </Link>
          ) : null
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-2 text-xs text-muted">
          <Badge tone="neutral">{counts.pending} pending</Badge>
          <Badge tone="ok">{counts.accepted} accepted</Badge>
          <Badge tone="info">{counts.edited} edited</Badge>
          <Badge tone="bad">{counts.rejected} rejected</Badge>
        </div>
        <div className="ml-auto flex items-center gap-1 rounded-lg border border-line p-1">
          {(['all', 'pending', 'decided'] as const).map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => setFilter(value)}
              aria-pressed={filter === value}
              className={
                filter === value
                  ? 'rounded-md bg-electric/20 px-3 py-1 text-xs font-semibold text-ink'
                  : 'rounded-md px-3 py-1 text-xs font-medium text-muted hover:text-ink'
              }
            >
              {value === 'all' ? 'All' : value === 'pending' ? 'Pending' : 'Decided'}
            </button>
          ))}
        </div>
      </div>

      {decision.isError ? (
        <ErrorNotice error={decision.error} title="That decision was not saved" />
      ) : null}

      {items.length === 0 ? (
        <EmptyState
          title="No recommendations for this analysis"
          body="Nothing in this resume tripped a rule, so there is nothing to correct. That is a real result, not a missing page."
          action={
            <Link to={`/app/analyses/${analysisId}`} className="btn-ghost">
              Back to the report
            </Link>
          }
        />
      ) : null}

      {items.length > 0 && visible.length === 0 ? (
        <EmptyState
          title="Nothing in this filter"
          body="Every card here has already been decided. Switch to All to review what you chose."
        />
      ) : null}

      {grouped.map((group) => (
        <section key={group.priority} aria-labelledby={`priority-${group.priority}`} className="flex flex-col gap-4">
          <div className="flex items-center gap-3">
            <h2 id={`priority-${group.priority}`} className="text-sm font-semibold uppercase tracking-[0.18em] text-muted">
              {group.priority} priority
            </h2>
            <span className="h-px flex-1 bg-line" aria-hidden="true" />
            <span className="text-xs text-muted">{group.rows.length}</span>
          </div>

          <ul className="flex flex-col gap-4">
            {group.rows.map((item) => {
              const decided = item.state !== 'pending'
              const isEditing = editingId === item.id
              const needsFact = !item.proposed_text && item.requires_user_input.length > 0

              return (
                <li key={item.id} className="panel overflow-hidden">
                  <div className="flex flex-wrap items-center gap-2 border-b border-line/70 px-5 py-3">
                    <Badge tone="info">{CATEGORY_LABELS[item.category]}</Badge>
                    <Badge tone={priorityTone(item.priority)}>{item.priority}</Badge>
                    <Badge tone="neutral">confidence {item.confidence}</Badge>
                    {item.state !== 'pending' ? <Badge tone={stateTone(item.state)}>{item.state}</Badge> : null}
                    {item.finding_id ? (
                      <span className="ml-auto font-mono text-[11px] text-muted/70">{item.finding_id}</span>
                    ) : null}
                  </div>

                  <div className="flex flex-col gap-4 px-5 py-4">
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div>
                        <p className="label">Original</p>
                        <p className="mt-2 whitespace-pre-wrap rounded-lg bg-white/5 p-3 text-sm text-muted">
                          {item.original_text ?? 'No specific line was cited.'}
                        </p>
                      </div>
                      <div>
                        <p className="label">Proposed</p>
                        <p className="mt-2 whitespace-pre-wrap rounded-lg border border-electric/30 bg-electric/5 p-3 text-sm text-ink">
                          {item.proposed_text ?? (needsFact ? 'Waiting for your input.' : 'No rewrite — see the fix below.')}
                        </p>
                      </div>
                    </div>

                    <div>
                      <p className="label">Why</p>
                      <p className="mt-1.5 text-sm leading-relaxed text-muted">{item.reason}</p>
                    </div>

                    {item.remediation ? (
                      <div>
                        <p className="label">What to do</p>
                        <p className="mt-1.5 text-sm leading-relaxed text-muted">{item.remediation}</p>
                      </div>
                    ) : null}

                    {item.requires_user_input.length > 0 ? (
                      <div className="rounded-xl border border-amber-400/30 bg-amber-400/5 p-4">
                        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-amber-300">
                          We will not invent this
                        </p>
                        <ul className="mt-2 flex flex-col gap-1.5">
                          {item.requires_user_input.map((prompt) => (
                            <li key={prompt.field} className="text-sm text-ink">
                              <span className="font-mono text-[11px] uppercase tracking-wide text-amber-300/80">
                                {prompt.field}
                              </span>
                              <span aria-hidden="true"> · </span>
                              {prompt.question}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}

                    {isEditing ? (
                      <div className="flex flex-col gap-2">
                        <label htmlFor={`edit-${item.id}`} className="label">
                          Your wording
                        </label>
                        <textarea
                          id={`edit-${item.id}`}
                          value={draft}
                          onChange={(event) => setDraft(event.target.value)}
                          rows={4}
                          className="w-full rounded-xl border border-line bg-void/60 px-3 py-2 text-sm text-ink focus:border-electric"
                          placeholder="Rewrite the line without adding anything that did not happen."
                        />
                        <div className="flex flex-wrap items-center gap-2">
                          <button
                            type="button"
                            className="btn-primary"
                            disabled={draft.trim().length === 0 || decision.isPending}
                            onClick={() =>
                              decision.mutate({ recommendationId: item.id, decision: 'edit', editedText: draft.trim() })
                            }
                          >
                            Save wording
                          </button>
                          <button
                            type="button"
                            className="btn-ghost"
                            onClick={() => {
                              setEditingId(null)
                              setDraft('')
                            }}
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex flex-wrap items-center gap-2">
                        <button
                          type="button"
                          className="btn-primary"
                          disabled={decided || decision.isPending}
                          onClick={() => decision.mutate({ recommendationId: item.id, decision: 'accept' })}
                        >
                          Accept
                        </button>
                        <button
                          type="button"
                          className="btn-ghost"
                          disabled={decided || decision.isPending}
                          onClick={() => decision.mutate({ recommendationId: item.id, decision: 'reject' })}
                        >
                          Reject
                        </button>
                        <button
                          type="button"
                          className="btn-ghost"
                          disabled={decided || decision.isPending}
                          onClick={() => {
                            setEditingId(item.id)
                            setDraft(item.proposed_text ?? item.original_text ?? '')
                          }}
                        >
                          Edit
                        </button>
                        {item.state === 'accepted' && resumeId ? (
                          <Link to={`/app/resumes/${resumeId}/studio`} className="btn-ghost ml-auto">
                            Apply in studio
                          </Link>
                        ) : null}
                      </div>
                    )}
                  </div>
                </li>
              )
            })}
          </ul>
        </section>
      ))}

      <div className="flex flex-wrap items-center gap-2">
        <Link to={`/app/analyses/${analysisId}`} className="btn-ghost">
          Back to the report
        </Link>
        <span className="text-xs text-muted">
          Severity follows the scoring finding; the score itself is never changed by a decision.
        </span>
      </div>
    </div>
  )
}
