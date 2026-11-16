import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { CheckCircle2, Info, TriangleAlert, X } from 'lucide-react'

type ToastTone = 'info' | 'success' | 'warning'

type ToastItem = {
  id: number
  message: string
  tone: ToastTone
}

type ToastContextValue = {
  showToast: (message: string, tone?: ToastTone) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

const toneIcons = {
  info: Info,
  success: CheckCircle2,
  warning: TriangleAlert,
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const nextId = useRef(1)

  const dismiss = useCallback((id: number) => {
    setToasts((list) => list.filter((item) => item.id !== id))
  }, [])

  const showToast = useCallback(
    (message: string, tone: ToastTone = 'info') => {
      const id = nextId.current
      nextId.current += 1
      setToasts((list) => [...list.slice(-2), { id, message, tone }])
      window.setTimeout(() => dismiss(id), 3200)
    },
    [dismiss],
  )

  const value = useMemo(() => ({ showToast }), [showToast])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-viewport" role="status" aria-live="polite">
        {toasts.map((toast) => {
          const Icon = toneIcons[toast.tone]
          return (
            <div className={`toast toast-${toast.tone}`} key={toast.id}>
              <Icon size={16} className="toast-icon" />
              <span>{toast.message}</span>
              <button
                type="button"
                className="toast-close"
                onClick={() => dismiss(toast.id)}
                aria-label="关闭提示"
              >
                <X size={14} />
              </button>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext)
  if (!context) {
    throw new Error('useToast 必须在 ToastProvider 内使用')
  }
  return context
}
