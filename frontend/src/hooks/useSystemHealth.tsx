import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import type { HealthData } from '../types'

type HealthState = {
  loading: boolean
  data: HealthData | null
  error: string | null
  checkedAt: string | null
}

type SystemHealthValue = HealthState & { refresh: () => Promise<void> }

const SystemHealthContext = createContext<SystemHealthValue | null>(null)

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'

/** 全局共享后端健康状态，避免多个页面重复请求。 */
export function SystemHealthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<HealthState>({
    loading: true,
    data: null,
    error: null,
    checkedAt: null,
  })

  const refresh = useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true, error: null }))
    try {
      const response = await fetch(`${API_BASE_URL}/health`)
      if (!response.ok) {
        throw new Error(`接口返回 HTTP ${response.status}`)
      }
      const data = (await response.json()) as HealthData
      setState({
        loading: false,
        data,
        error: null,
        checkedAt: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
      })
    } catch (error) {
      setState({
        loading: false,
        data: null,
        error: error instanceof Error ? error.message : '未知错误',
        checkedAt: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
      })
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const value = useMemo(() => ({ ...state, refresh }), [state, refresh])

  return <SystemHealthContext.Provider value={value}>{children}</SystemHealthContext.Provider>
}

export function useSystemHealth(): SystemHealthValue {
  const context = useContext(SystemHealthContext)
  if (!context) {
    throw new Error('useSystemHealth 必须在 SystemHealthProvider 内使用')
  }
  return context
}
