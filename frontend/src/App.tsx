import type { ReactElement } from 'react'
import { AppLayout } from './components/layout/AppLayout'
import { ToastProvider } from './components/ui/Toast'
import { useHashRoute, type RouteKey } from './hooks/useHashRoute'
import { SystemHealthProvider } from './hooks/useSystemHealth'
import { AnalyzePage } from './pages/AnalyzePage'
import { DashboardPage } from './pages/DashboardPage'
import { MattersPage } from './pages/MattersPage'
import { RisksPage } from './pages/RisksPage'
import { SettingsPage } from './pages/SettingsPage'
import { TasksPage } from './pages/TasksPage'
import { VerificationPage } from './pages/VerificationPage'

function App() {
  const { route, params, navigate } = useHashRoute()

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

  return (
    <SystemHealthProvider>
      <ToastProvider>
        <AppLayout current={route} onNavigate={navigate}>
          {pages[route]}
        </AppLayout>
      </ToastProvider>
    </SystemHealthProvider>
  )
}

export default App
