import { useEffect, useState, type ReactNode } from 'react'
import type { RouteKey } from '../../hooks/useHashRoute'
import { Sidebar } from './Sidebar'
import { Topbar } from './Topbar'

type AppLayoutProps = {
  current: RouteKey
  onNavigate: (key: RouteKey) => void
  children: ReactNode
}

export function AppLayout({ current, onNavigate, children }: AppLayoutProps) {
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
        <Topbar current={current} onMenu={() => setDrawerOpen(true)} onNavigate={onNavigate} />
        <main className="page-content">{children}</main>
      </div>
    </div>
  )
}
