import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { Brand } from '../components/Brand'
import { ErrorNotice } from '../components/States'
import { useAuth } from '../context/AuthContext'

const MIN_PASSWORD_LENGTH = 12

interface FieldErrors {
  email?: string
  password?: string
  confirm?: string
}

export function RegisterPage() {
  const { status, register } = useAuth()
  const navigate = useNavigate()

  const [displayName, setDisplayName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [error, setError] = useState<unknown>(null)
  const [pending, setPending] = useState(false)

  if (status === 'authenticated') {
    return <Navigate to="/app" replace />
  }

  function validate(): boolean {
    const errors: FieldErrors = {}

    if (!email.trim()) {
      errors.email = 'Enter the email address you want to use.'
    }

    if (password.length < MIN_PASSWORD_LENGTH) {
      errors.password = `Use at least ${MIN_PASSWORD_LENGTH} characters — the API rejects anything shorter.`
    }

    if (password !== confirm) {
      errors.confirm = 'The two passwords do not match.'
    }

    setFieldErrors(errors)
    return Object.keys(errors).length === 0
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault()
    setError(null)
    if (!validate()) {
      return
    }

    setPending(true)
    try {
      const name = displayName.trim()
      await register(email.trim(), password, name.length > 0 ? name : undefined)
      navigate('/app', { replace: true })
    } catch (caught) {
      setError(caught)
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="border-b border-line/70">
        <div className="mx-auto flex w-full max-w-5xl items-center justify-between px-4 py-4 sm:px-6">
          <Link to="/" aria-label="POTENCIA — home" className="rounded-md">
            <Brand />
          </Link>
          <Link to="/login" className="text-sm font-medium text-muted hover:text-ink">
            Sign in
          </Link>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center px-4 py-12 sm:px-6">
        <p className="label">Create account</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-ink">
          Measure the resume you <span className="gradient-text">actually have.</span>
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-muted">
          Every score comes from explicit rules and cites the text behind it. Nothing is invented,
          and nothing is shared with another account.
        </p>

        <form onSubmit={handleSubmit} className="panel mt-8 flex flex-col gap-5 p-6" noValidate>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="display-name" className="text-sm font-medium text-ink">
              Name <span className="font-normal text-muted">(optional)</span>
            </label>
            <input
              id="display-name"
              name="name"
              type="text"
              autoComplete="name"
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              className="rounded-xl border border-line bg-void/70 px-3 py-2 text-sm text-ink placeholder:text-muted/60 focus:border-electric/60"
              placeholder="How your dashboard greets you"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="email" className="text-sm font-medium text-ink">
              Email
            </label>
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              aria-invalid={fieldErrors.email ? true : undefined}
              aria-describedby={fieldErrors.email ? 'email-error' : undefined}
              className="rounded-xl border border-line bg-void/70 px-3 py-2 text-sm text-ink placeholder:text-muted/60 focus:border-electric/60"
              placeholder="you@example.com"
            />
            {fieldErrors.email ? (
              <p id="email-error" className="text-xs text-rose-300">
                {fieldErrors.email}
              </p>
            ) : null}
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="password" className="text-sm font-medium text-ink">
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="new-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              aria-invalid={fieldErrors.password ? true : undefined}
              aria-describedby={fieldErrors.password ? 'password-error' : 'password-hint'}
              className="rounded-xl border border-line bg-void/70 px-3 py-2 text-sm text-ink placeholder:text-muted/60 focus:border-electric/60"
              placeholder={`At least ${MIN_PASSWORD_LENGTH} characters`}
            />
            {fieldErrors.password ? (
              <p id="password-error" className="text-xs text-rose-300">
                {fieldErrors.password}
              </p>
            ) : (
              <p id="password-hint" className="text-xs text-muted">
                {MIN_PASSWORD_LENGTH} characters or more. Length is the requirement — the API
                enforces no other rule.
              </p>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="confirm-password" className="text-sm font-medium text-ink">
              Confirm password
            </label>
            <input
              id="confirm-password"
              name="confirm-password"
              type="password"
              autoComplete="new-password"
              required
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
              aria-invalid={fieldErrors.confirm ? true : undefined}
              aria-describedby={fieldErrors.confirm ? 'confirm-error' : undefined}
              className="rounded-xl border border-line bg-void/70 px-3 py-2 text-sm text-ink placeholder:text-muted/60 focus:border-electric/60"
              placeholder="Type it again"
            />
            {fieldErrors.confirm ? (
              <p id="confirm-error" className="text-xs text-rose-300">
                {fieldErrors.confirm}
              </p>
            ) : null}
          </div>

          {error ? <ErrorNotice error={error} title="Could not create the account" /> : null}

          <button type="submit" className="btn-primary w-full" disabled={pending}>
            {pending ? 'Creating account…' : 'Create account'}
          </button>

          <p className="text-xs leading-relaxed text-muted">
            Scores are deterministic and reproducible. The ATS figure is a compatibility estimate,
            not a prediction that any employer will progress your application.
          </p>
        </form>

        <p className="mt-6 text-sm text-muted">
          Already have an account?{' '}
          <Link to="/login" className="font-semibold text-ink underline decoration-electric/60">
            Sign in
          </Link>
          .
        </p>
      </main>
    </div>
  )
}
