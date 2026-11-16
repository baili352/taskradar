import { Menu } from 'lucide-react'
import { getNavItem } from '../../config/navigation'
import type { RouteKey } from '../../hooks/useHashRoute'
import { useSystemHealth } from '../../hooks/useSystemHealth'

type TopbarProps = {
  current: RouteKey
  onMenu: () => void
  onNavigate: (key: RouteKey) => void
}

export function Topbar({ current, onMenu, onNavigate }: TopbarProps) {
  const { data, loading, error } = useSystemHealth()
  const online = data?.status === 'ok'
  const nav = getNavItem(current)

  const statusText = loading ? '检测中' : online ? '系统正常' : error ? '后端未连接' : '状态未知'
  const statusClass = loading ? 'pending' : online ? 'online' : 'offline'

  return (
    <header className="topbar">
      <div className="topbar-left">
        <button type="button" className="icon-btn menu-btn" onClick={onMenu} aria-label="打开导航">
          <Menu size={20} />
        </button>
        <div className="topbar-title">
          <span>{nav.label}</span>
          <small>{nav.description}</small>
        </div>
      </div>

      <div className="topbar-right">
        <button
          type="button"
          className={`health-pill ${statusClass}`}
          onClick={() => onNavigate('settings')}
          title="查看系统运行信息"
        >
          <span className="dot" />
          {statusText}
        </button>
        <div className="user-chip">
          <span className="avatar">体</span>
          <div className="user-meta">
            <strong>体验用户</strong>
            <small>演示账号</small>
          </div>
        </div>
      </div>
    </header>
  )
}
