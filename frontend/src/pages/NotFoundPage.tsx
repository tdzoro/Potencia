import { Link } from 'react-router-dom'

export function NotFoundPage() {
  return (
    <div className="max-w-xl">
      <p className="label">404</p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
        This page does not exist
      </h1>
      <p className="mt-4 text-base leading-relaxed text-muted">
        The address you followed is not part of POTENCIA. It may have been mistyped, or the page has
        not been built yet.
      </p>
      <Link to="/" className="btn-ghost mt-8">
        Back to overview
      </Link>
    </div>
  )
}
