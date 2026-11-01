import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Brand } from '../components/Brand'
import { ErrorNotice } from '../components/States'
import { resetPassword } from '../services/auth'

const MIN_PASSWORD_LENGTH = 12

export function ResetPasswordPage() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')

  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [fieldErrors, setFieldErrors] = useState<{ password?: string; confirm?: string }>({})
  const [error, setError] = useState<unknown>(null)
  const [pending, setPending] = useState(false)
  const [success, setSuccess] = useState(false)

  function validate(): boolean {
    const errors: { password?: string; confirm?: string } = {}
    if (password.length < MIN_PASSWORD_LENGTH) {
      errors.password = `Passwords must be at least ${MIN_PASSWORD_LENGTH} characters long.`
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
    if (!token) {
      setError(new Error('Missing password reset token in URL.'))
      return
    }
    if (!validate()) {
      return
    }

    setPending(true)
    try {
      await resetPassword(token, password)
      setSuccess(true)
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
        <p className="label">Security</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-ink">
          Set new <span className="gradient-text">password.</span>
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-muted">
          Choose a strong password of at least 12 characters. All previous active sessions will be invalidated.
        </p>

        {!token ? (
          <div className="panel mt-8 flex flex-col gap-4 p-6">
            <span className="label text-rose-300">Invalid link</span>
            <p className="text-sm text-ink">No reset token was found in the link.</p>
            <Link to="/forgot-password" className="btn-secondary text-center text-sm">
              Request a new password reset link
            </Link>
          </div>
        ) : success ? (
          <div className="panel mt-8 flex flex-col items-center gap-5 p-8 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-400">
              <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h2 className="text-2xl font-semibold text-ink">Password updated!</h2>
            <p className="text-sm text-muted leading-relaxed">
              Your password has been securely reset. You can now log in using your new credentials.
            </p>
            <Link to="/login" className="btn-primary mt-2 w-full text-center">
              Sign in with new password &rarr;
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="panel mt-8 flex flex-col gap-5 p-6" noValidate>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="new-password" className="text-sm font-medium text-ink">
                New password
              </label>
              <input
                id="new-password"
                type="password"
                autoComplete="new-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="rounded-xl border border-line bg-void/70 px-3 py-2 text-sm text-ink placeholder:text-muted/60 focus:border-electric/60"
                placeholder={`At least ${MIN_PASSWORD_LENGTH} characters`}
              />
              {fieldErrors.password ? (
                <p className="text-xs text-rose-300">{fieldErrors.password}</p>
              ) : null}
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="confirm-password" className="text-sm font-medium text-ink">
                Confirm new password
              </label>
              <input
                id="confirm-password"
                type="password"
                autoComplete="new-password"
                required
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                className="rounded-xl border border-line bg-void/70 px-3 py-2 text-sm text-ink placeholder:text-muted/60 focus:border-electric/60"
                placeholder="Type your new password again"
              />
              {fieldErrors.confirm ? (
                <p className="text-xs text-rose-300">{fieldErrors.confirm}</p>
              ) : null}
            </div>

            {error ? <ErrorNotice error={error} title="Could not reset password" /> : null}

            <button type="submit" className="btn-primary w-full" disabled={pending}>
              {pending ? 'Updating password…' : 'Update password'}
            </button>

            <div className="text-center">
              <Link to="/forgot-password" className="text-xs text-muted hover:text-ink">
                Link expired or need a new one? <span className="text-ink font-semibold underline decoration-electric/60">Request new reset link</span>
              </Link>
            </div>
          </form>
        )}
      </main>
    </div>
  )
}

