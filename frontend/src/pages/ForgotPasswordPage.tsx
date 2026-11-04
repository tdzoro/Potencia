import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Brand } from '../components/Brand'
import { ErrorNotice } from '../components/States'
import { forgotPassword } from '../services/auth'

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<unknown>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault()
    setError(null)
    if (!email.trim()) {
      return
    }

    setPending(true)
    try {
      await forgotPassword(email.trim())
      setSubmitted(true)
    } catch (caught) {
      // Return same generic success view or display error if unexpected network fault
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
        <p className="label">Account recovery</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-ink">
          Reset your <span className="gradient-text">password.</span>
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-muted">
          Enter your registered email address and we will send you a secure one-time link to reset your password.
        </p>

        {submitted ? (
          <div className="panel mt-8 flex flex-col gap-5 p-6">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-400">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
            </div>
            <div>
              <h2 className="text-lg font-semibold text-ink">Check your email</h2>
              <p className="mt-2 text-sm text-muted leading-relaxed">
                If an account exists with <span className="text-ink font-medium">{email}</span>, an email with password recovery instructions has been dispatched.
              </p>
              <p className="mt-2 text-xs text-muted">
                The recovery link is valid for 60 minutes and can be used once. Check your spam folder if it doesn't appear within a few minutes.
              </p>
            </div>
            <Link to="/login" className="btn-secondary w-full text-center text-sm">
              Back to Sign in
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="panel mt-8 flex flex-col gap-5 p-6" noValidate>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="recovery-email" className="text-sm font-medium text-ink">
                Email address
              </label>
              <input
                id="recovery-email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="rounded-xl border border-line bg-void/70 px-3 py-2 text-sm text-ink placeholder:text-muted/60 focus:border-electric/60"
                placeholder="you@example.com"
              />
            </div>

            {error ? <ErrorNotice error={error} title="Could not process request" /> : null}

            <button type="submit" className="btn-primary w-full" disabled={pending || !email}>
              {pending ? 'Sending reset link…' : 'Send password reset link'}
            </button>

            <div className="text-center">
              <Link to="/login" className="text-xs text-muted hover:text-ink">
                Remember your password? <span className="text-ink font-semibold underline decoration-electric/60">Sign in</span>
              </Link>
            </div>
          </form>
        )}
      </main>
    </div>
  )
}

