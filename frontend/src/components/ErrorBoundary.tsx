import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'

interface ErrorBoundaryProps {
  children: ReactNode
}

interface ErrorBoundaryState {
  error: Error | null
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('Unhandled interface error', error, info.componentStack)
  }

  private handleReload = (): void => {
    window.location.reload()
  }

  render(): ReactNode {
    const { error } = this.state

    if (!error) {
      return this.props.children
    }

    return (
      <div className="flex min-h-dvh items-center justify-center px-6">
        <div className="panel w-full max-w-lg p-8">
          <p className="label">Interface error</p>
          <h1 className="mt-3 text-2xl font-semibold text-ink">Something broke while rendering</h1>
          <p className="mt-3 text-sm leading-relaxed text-muted">
            The interface stopped unexpectedly. Reloading usually clears it. No analysis data was
            changed by this failure.
          </p>
          <p className="mt-4 break-words rounded-lg border border-line bg-void/60 p-3 font-mono text-xs text-rose-300">
            {error.message}
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <button type="button" onClick={this.handleReload} className="btn-primary">
              Reload the page
            </button>
            <a href="/" className="btn-ghost">
              Back to overview
            </a>
          </div>
        </div>
      </div>
    )
  }
}
