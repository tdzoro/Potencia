import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Brand } from '../components/Brand'
import { ErrorNotice } from '../components/States'
import { resendVerification, verifyEmail } from '../services/auth'

export function VerifyEmailPage() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')

  const [status, setStatus] = useState<'verifying' | 'success' | 'error' | 'no_token'>('verifying')
  const [errorMessage, setErrorMessage] = useState<unknown>(null)
  const [resendEmail, setResendEmail] = useState('')
  const [resendPending, setResendPending] = useState(false)
  const [resendNotice, setResendNotice] = useState<string | null>(null)

  useEffect(() => {
    if (!token) {
      setStatus('no_token')
      return
    }

    let isMounted = true
    verifyEmail(token)
      .then(() => {
        if (isMounted) {
          setStatus('success')
        }
      })
      .catch((err) => {
        if (isMounted) {
          setStatus('error')
          setErrorMessage(err)
        }
      })

    return () => {
      isMounted = false
    }
  }, [token])

  async function handleResend(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault()
    if (!resendEmail.trim()) {
      return
    }
    setResendPending(true)
    setResendNotice(null)
    try {
      const response = await resendVerification(resendEmail.trim())
      setResendNotice(response.message || 'If an unverified account exists, a link was sent.')
    } catch {
      setResendNotice('If an unverified account exists, a link was sent.')
    } finally {
      setResendPending(false)
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
        {status === 'verifying' ? (
          <div className="panel flex flex-col items-center gap-4 p-8 text-center">
            <span className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-electric border-t-transparent" />
            <h1 className="text-xl font-semibold text-ink">Verifying your email…</h1>
            <p className="text-sm text-muted">Confirming your cryptographic verification token.</p>
          </div>
        ) : null}

        {status === 'success' ? (
          <div className="panel flex flex-col items-center gap-5 p-8 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-400">
              <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h1 className="text-2xl font-semibold text-ink">Email verified!</h1>
            <p className="text-sm text-muted leading-relaxed">
              Your account is now fully activated. You can now sign in and access the complete resume intelligence suite.
            </p>
            <Link to="/login" className="btn-primary mt-2 w-full text-center">
              Continue to Sign in &rarr;
            </Link>
          </div>
        ) : null}

        {status === 'error' || status === 'no_token' ? (
          <div className="panel flex flex-col gap-6 p-6">
            <div className="flex flex-col gap-2">
              <span className="label text-rose-300">Verification issue</span>
              <h1 className="text-xl font-semibold text-ink">
                {status === 'no_token' ? 'Missing verification link' : 'Invalid or expired link'}
              </h1>
              <p className="text-sm text-muted leading-relaxed">
                {status === 'no_token'
                  ? 'No verification token was provided in the URL.'
                  : 'This email verification link may have expired (24-hour lifetime) or has already been used.'}
              </p>
            </div>

            {errorMessage ? <ErrorNotice error={errorMessage} title="Verification failed" /> : null}

            <form onSubmit={handleResend} className="flex flex-col gap-3 border-t border-line/60 pt-4">
              <p className="text-xs font-medium text-ink">Need a new verification link?</p>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="resend-email" className="sr-only">Email address</label>
                <input
                  id="resend-email"
                  type="email"
                  required
                  placeholder="Enter your registered email"
                  value={resendEmail}
                  onChange={(e) => setResendEmail(e.target.value)}
                  className="rounded-xl border border-line bg-void/70 px-3 py-2 text-sm text-ink placeholder:text-muted/60 focus:border-electric/60"
                />
              </div>

              {resendNotice ? (
                <p className="text-xs text-emerald-300">{resendNotice}</p>
              ) : null}

              <button type="submit" className="btn-secondary w-full text-sm" disabled={resendPending || !resendEmail}>
                {resendPending ? 'Sending…' : 'Resend verification link'}
              </button>
            </form>

            <div className="border-t border-line/60 pt-3 text-center">
              <Link to="/login" className="text-xs font-semibold text-ink hover:underline">
                Back to Sign in
              </Link>
            </div>
          </div>
        ) : null}
      </main>
    </div>
  )
}

