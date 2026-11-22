import { useEffect, useState, type ReactNode } from 'react'
import type { AuthUser } from '../../api/auth'
import type { RouteKey } from '../../hooks/useHashRoute'
import { Sidebar } from './Sidebar'
import { Topbar } from './Topbar'

type AppLayoutProps = {
  current: RouteKey
  onNavigate: (key: RouteKey) => void
  user?: AuthUser | null
  onLogout?: () => void
  children: ReactNode
}

export function AppLayout({
  current,
  onNavigate,
  user,
  onLogout,
  children,
}: AppLayoutProps) {
  const [drawerOpen, setDrawerOpen] = useState(false)

  useEffect(() => {
    setDrawerOpen(false)
  }, [current])

  return (
    <div className="app-shell">
      <Sidebar
        current={current}
        onNavigate={onNavigate}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      />
      <div className="main-area">
        <Topbar
          current={current}
          onMenu={() => setDrawerOpen(true)}
          onNavigate={onNavigate}
          user={user}
          onLogout={onLogout}
        />
        <main className="page-content">{children}</main>
      </div>
    </div>
  )
}
