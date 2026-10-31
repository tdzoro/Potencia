import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { Brand } from '../components/Brand'
import { ErrorNotice } from '../components/States'
import { useAuth } from '../context/AuthContext'

export function LoginPage() {
  const { status, login } = useAuth()
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<unknown>(null)
  const [pending, setPending] = useState(false)

  if (status === 'authenticated') {
    return <Navigate to="/app" replace />
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault()
    setError(null)
    setPending(true)
    try {
      await login(email.trim(), password)
      navigate('/app', { replace: true })
    } catch (caught) {
      // The server's own message: it is already specific about what failed.
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
          <Link to="/register" className="text-sm font-medium text-muted hover:text-ink">
            Create an account
          </Link>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center px-4 py-12 sm:px-6">
        <p className="label">Sign in</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-ink">
          Continue to your <span className="gradient-text">reports.</span>
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-muted">
          Your resumes, analyses and approved revisions are private to this account.
        </p>

        <form onSubmit={handleSubmit} className="panel mt-8 flex flex-col gap-5 p-6" noValidate>
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
              className="rounded-xl border border-line bg-void/70 px-3 py-2 text-sm text-ink placeholder:text-muted/60 focus:border-electric/60"
              placeholder="you@example.com"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="password" className="text-sm font-medium text-ink">
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="rounded-xl border border-line bg-void/70 px-3 py-2 text-sm text-ink placeholder:text-muted/60 focus:border-electric/60"
              placeholder="Your password"
            />
          </div>

          {error ? <ErrorNotice error={error} title="Could not sign in" /> : null}

          <button type="submit" className="btn-primary w-full" disabled={pending}>
            {pending ? 'Signing in…' : 'Sign in'}
          </button>

          <p className="text-xs leading-relaxed text-muted">
            New accounts need a password of at least 12 characters. Signing in accepts whatever
            password the account was created with.
          </p>
        </form>

        <p className="mt-6 text-sm text-muted">
          No account yet?{' '}
          <Link to="/register" className="font-semibold text-ink underline decoration-electric/60">
            Create one
          </Link>
          .
        </p>
      </main>
    </div>
  )
}
