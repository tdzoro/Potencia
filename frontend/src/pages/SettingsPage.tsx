/**
 * Account settings, data explanation and account deletion.
 *
 * The privacy block states what the system actually stores, in the same words
 * the API uses. It is not marketing copy: an export really is deleted after its
 * retention window, the original parse really is immutable, and the scores
 * really are computed by rules rather than guessed by a model.
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ErrorNotice, PageHeader } from '../components/States'
import { useAuth } from '../context/AuthContext'
import { deleteAccount } from '../services/auth'

interface Fact {
  title: string
  body: string
}

const stored: Fact[] = [
  {
    title: 'The documents you upload',
    body: 'Stored on the server under a content-addressed key and never served from a public path. Two uploads of identical bytes share one object.',
  },
  {
    title: 'The parsed structure',
    body: 'Sections, entries, bullets and skills extracted from your document, with the character span each bullet occupied so evidence can be quoted back to you.',
  },
  {
    title: 'Scores, findings and recommendations',
    body: 'Each analysis stores its numbers with the methodology version that produced them, so an old report never silently changes meaning.',
  },
  {
    title: 'Revisions and exports',
    body: 'Revision 0 is the untouched parse; every edit you approve is a new version, never an overwrite. Export files expire and are removed on request.',
  },
]

const guarantees: Fact[] = [
  {
    title: 'Scores come from rules, not a model',
    body: 'Every number is produced by a deterministic criterion with a documented weight. Re-running the same resume produces the same score.',
  },
  {
    title: 'Nothing is invented',
    body: 'POTENCIA will not add achievements, employers, skills or metrics you did not write. When a bullet needs a number, it asks you for it.',
  },
  {
    title: 'Your data is yours to remove',
    body: 'Deleting a resume removes its derived analyses, recommendations, revisions and exports. Deleting your account removes all of it.',
  },
]

function formatDate(iso: string | undefined): string {
  if (!iso) {
    return '—'
  }
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) {
    return iso
  }
  return date.toLocaleDateString(undefined, { dateStyle: 'long' })
}

export function SettingsPage() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [confirming, setConfirming] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [failure, setFailure] = useState<unknown>(null)

  async function handleSignOut(): Promise<void> {
    await logout()
    navigate('/', { replace: true })
  }

  async function handleDelete(): Promise<void> {
    setDeleting(true)
    setFailure(null)
    try {
      await deleteAccount()
      navigate('/', { replace: true })
    } catch (error) {
      setFailure(error)
      setDeleting(false)
      setConfirming(false)
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        eyebrow="Account"
        title="Settings"
        description="Your account, what POTENCIA stores about you, and how to remove it."
      />

      {failure ? (
        <ErrorNotice
          error={failure}
          title="The account could not be deleted"
          onRetry={() => setFailure(null)}
        />
      ) : null}

      <section aria-labelledby="account-heading" className="panel p-5 sm:p-6">
        <h2 id="account-heading" className="text-lg font-semibold text-ink">
          Account
        </h2>

        <dl className="mt-5 grid gap-4 sm:grid-cols-3">
          <div>
            <dt className="label">Email</dt>
            <dd className="mt-1 truncate text-sm text-ink" title={user?.email}>
              {user?.email ?? '—'}
            </dd>
          </div>
          <div>
            <dt className="label">Display name</dt>
            <dd className="mt-1 truncate text-sm text-ink">{user?.display_name ?? 'Not set'}</dd>
          </div>
          <div>
            <dt className="label">Member since</dt>
            <dd className="mt-1 text-sm text-ink">{formatDate(user?.created_at)}</dd>
          </div>
        </dl>

        <div className="mt-6 flex flex-wrap items-center gap-2">
          <button type="button" className="btn-ghost" onClick={() => void handleSignOut()}>
            Sign out
          </button>
          <p className="text-xs text-muted">
            Signing out revokes this account's refresh tokens. Access tokens expire within 15 minutes.
          </p>
        </div>
      </section>

      <section aria-labelledby="stored-heading" className="panel p-5 sm:p-6">
        <h2 id="stored-heading" className="text-lg font-semibold text-ink">
          What is stored
        </h2>
        <ul className="mt-4 grid gap-4 sm:grid-cols-2">
          {stored.map((item) => (
            <li key={item.title}>
              <p className="text-sm font-semibold text-ink">{item.title}</p>
              <p className="mt-1 text-sm leading-relaxed text-muted">{item.body}</p>
            </li>
          ))}
        </ul>

        <h3 className="mt-8 text-sm font-semibold uppercase tracking-[0.14em] text-muted">
          Guarantees
        </h3>
        <ul className="mt-3 grid gap-4 sm:grid-cols-3">
          {guarantees.map((item) => (
            <li key={item.title}>
              <p className="text-sm font-semibold text-ink">{item.title}</p>
              <p className="mt-1 text-sm leading-relaxed text-muted">{item.body}</p>
            </li>
          ))}
        </ul>
      </section>

      <section
        aria-labelledby="danger-heading"
        className="panel border-rose-400/30 p-5 sm:p-6"
      >
        <h2 id="danger-heading" className="text-lg font-semibold text-rose-200">
          Delete account
        </h2>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">
          This permanently deletes your account and everything attached to it: uploaded resumes, parsed
          structures, analyses, recommendations, revisions and export files. There is no recovery and no
          grace period.
        </p>

        {confirming ? (
          <div className="mt-4 flex flex-col gap-3 rounded-xl border border-rose-400/30 bg-rose-400/5 p-4">
            <p className="text-sm text-rose-100">
              Delete <span className="font-semibold">{user?.email ?? 'this account'}</span> and all of its
              data? This cannot be undone.
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => void handleDelete()}
                disabled={deleting}
                className="inline-flex items-center rounded-xl border border-rose-400/40 bg-rose-500/20 px-4 py-2 text-sm font-semibold text-rose-100 hover:bg-rose-500/30 disabled:opacity-60"
              >
                {deleting ? 'Deleting…' : 'Yes, delete everything'}
              </button>
              <button
                type="button"
                onClick={() => setConfirming(false)}
                disabled={deleting}
                className="btn-ghost"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setConfirming(true)}
            className="mt-4 inline-flex items-center rounded-xl border border-rose-400/40 bg-rose-500/10 px-4 py-2 text-sm font-semibold text-rose-200 hover:bg-rose-500/20"
          >
            Delete my account
          </button>
        )}
      </section>
    </div>
  )
}
