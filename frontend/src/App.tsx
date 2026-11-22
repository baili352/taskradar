import { useEffect, useState, type ReactElement } from 'react'
import { fetchAuthState, logout, type AuthState } from './api/auth'
import { AppLayout } from './components/layout/AppLayout'
import { ToastProvider } from './components/ui/Toast'
import { useHashRoute, type RouteKey } from './hooks/useHashRoute'
import { SystemHealthProvider } from './hooks/useSystemHealth'
import { AnalyzePage } from './pages/AnalyzePage'
import { DashboardPage } from './pages/DashboardPage'
import { LoginPage } from './pages/LoginPage'
import { MattersPage } from './pages/MattersPage'
import { RisksPage } from './pages/RisksPage'
import { SettingsPage } from './pages/SettingsPage'
import { TasksPage } from './pages/TasksPage'
import { VerificationPage } from './pages/VerificationPage'

function App() {
  const { route, params, navigate } = useHashRoute()
  const [auth, setAuth] = useState<AuthState | null>(null)

  useEffect(() => {
    let alive = true
    fetchAuthState()
      .then((state) => {
        if (alive) setAuth(state)
      })
      .catch(() => {
        // 登录态接口异常时退化为「未开启登录」，避免整站白屏。
        if (alive) setAuth({ enabled: false, authenticated: false, user: null })
      })
    return () => {
      alive = false
    }
  }, [])

  const numericParam = (key: string): number | undefined => {
    const value = Number(params[key])
    return Number.isInteger(value) && value > 0 ? value : undefined
  }
  const focusMatterId = numericParam('matter')
  const focusTaskId = numericParam('task')
  const focusMaterialId = numericParam('material')

  const pages: Record<RouteKey, ReactElement> = {
    dashboard: <DashboardPage onNavigate={navigate} />,
    analyze: <AnalyzePage onNavigate={navigate} />,
    matters: <MattersPage onNavigate={navigate} focusMatterId={focusMatterId} />,
    verification: (
      <VerificationPage
        focusMatterId={focusMatterId}
        focusMaterialId={focusMaterialId}
      />
    ),
    tasks: <TasksPage focusMatterId={focusMatterId} focusTaskId={focusTaskId} />,
    risks: <RisksPage onNavigate={navigate} />,
    settings: <SettingsPage />,
  }

  if (!auth) {
    return <div className="boot-screen">正在加载…</div>
  }

  if (auth.enabled && !auth.authenticated) {
    return (
      <ToastProvider>
        <LoginPage onAuthenticated={setAuth} />
      </ToastProvider>
    )
  }

  const handleLogout = async () => {
    try {
      setAuth(await logout())
    } catch {
      setAuth({ enabled: auth.enabled, authenticated: false, user: null })
    }
  }

  return (
    <SystemHealthProvider>
      <ToastProvider>
        <AppLayout
          current={route}
          onNavigate={navigate}
          user={auth.user}
          onLogout={handleLogout}
        >
          {pages[route]}
        </AppLayout>
      </ToastProvider>
    </SystemHealthProvider>
  )
}

export default App
