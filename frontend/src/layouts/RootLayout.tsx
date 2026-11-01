import { NavLink, Outlet } from 'react-router-dom'
import { Brand } from '../components/Brand'
import { cn } from '../utils/cn'

interface NavItem {
  to: string
  label: string
  end: boolean
}

const navItems: NavItem[] = [
  { to: '/', label: 'Overview', end: true },
  { to: '/status', label: 'System status', end: false },
]

export function RootLayout() {
  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-surface focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-ink"
      >
        Skip to content
      </a>

      <header className="sticky top-0 z-40 border-b border-line/70 bg-void/80 backdrop-blur">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <NavLink
            to="/"
            aria-label="POTENCIA — home"
            className="shrink-0 rounded-md focus-visible:ring-2 focus-visible:ring-electric"
          >
            <Brand />
          </NavLink>

          <nav aria-label="Primary" className="flex items-center gap-1">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cn(
                    'rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-electric/15 text-ink'
                      : 'text-muted hover:bg-white/5 hover:text-ink',
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
            {/* Without these two links a visitor had no route to the product
                short of typing the URL. */}
            <NavLink to="/login" className="rounded-lg px-3 py-2 text-sm font-medium text-muted transition-colors hover:bg-white/5 hover:text-ink">
              Sign in
            </NavLink>
            <NavLink to="/register" className="btn-primary ml-1 px-3 py-1.5 text-xs">
              Get started
            </NavLink>
          </nav>
        </div>
      </header>

      <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-10 sm:px-6 lg:py-16">
        <Outlet />
      </main>

      <footer className="border-t border-line/70">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-3 px-4 py-8 text-sm text-muted sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p>
            <span className="font-semibold text-ink">POTENCIA</span>
            <span aria-hidden="true"> · </span>
            Beyond Your Resume. Unleash Your Potential.
          </p>
          <p className="text-xs">Proprietary · © 2026 POTENCIA Team · All rights reserved.</p>
        </div>
      </footer>
    </div>
  )
}
