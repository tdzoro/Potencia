import { NavLink, Navigate, Outlet, useLocation } from 'react-router-dom'
import { Brand } from '../components/Brand'
import { useAuth } from '../context/AuthContext'
import { cn } from '../utils/cn'

interface NavItem {
  to: string
  label: string
  end?: boolean
}

const navItems: NavItem[] = [
  { to: '/app', label: 'Dashboard', end: true },
  { to: '/app/upload', label: 'New analysis' },
  { to: '/app/history', label: 'History' },
  { to: '/app/settings', label: 'Settings' },
]

export function AppLayout() {
  const { status, user, logout } = useAuth()
  const location = useLocation()

  if (status === 'loading') {
    return (
      <div className="flex min-h-dvh items-center justify-center text-sm text-muted">
        Restoring your session…
      </div>
    )
  }

  if (status === 'anonymous') {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-40 border-b border-line/70 bg-void/85 backdrop-blur">
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-3 px-4 py-3 sm:px-6 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center justify-between gap-4">
            <NavLink to="/" aria-label="POTENCIA — home" className="shrink-0 rounded-md">
              <Brand />
            </NavLink>
            <div className="flex items-center gap-2 lg:hidden">
              <button type="button" className="btn-ghost" onClick={() => void logout()}>
                Sign out
              </button>
            </div>
          </div>

          <nav aria-label="Application" className="flex items-center gap-1 overflow-x-auto">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cn(
                    'whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                    isActive ? 'bg-electric/15 text-ink' : 'text-muted hover:bg-white/5 hover:text-ink',
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="hidden items-center gap-3 lg:flex">
            <span className="max-w-[180px] truncate text-xs text-muted" title={user?.email}>
              {user?.display_name ?? user?.email}
            </span>
            <button type="button" className="btn-ghost" onClick={() => void logout()}>
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main id="main" className="mx-auto w-full max-w-7xl flex-1 px-4 py-8 sm:px-6 lg:py-12">
        <Outlet />
      </main>

      <footer className="border-t border-line/70">
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-2 px-4 py-6 text-xs text-muted sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p>
            <span className="font-semibold text-ink">POTENCIA</span> · Beyond Your Resume. Unleash Your
            Potential.
          </p>
          <p>
            Scores are deterministic. ATS figures are compatibility estimates, not screening
            guarantees.
          </p>
        </div>
      </footer>
    </div>
  )
}
