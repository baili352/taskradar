import { Radar, X } from 'lucide-react'
import { navItems } from '../../config/navigation'
import type { RouteKey } from '../../hooks/useHashRoute'
import { APP_STAGE, APP_VERSION } from '../../lib/version'

type SidebarProps = {
  current: RouteKey
  onNavigate: (key: RouteKey) => void
  open: boolean
  onClose: () => void
}

export function Sidebar({ current, onNavigate, open, onClose }: SidebarProps) {
  return (
    <>
      <div
        className={`sidebar-overlay ${open ? 'visible' : ''}`.trim()}
        aria-hidden="true"
        onClick={onClose}
      />
      <aside className={`sidebar ${open ? 'open' : ''}`.trim()}>
        <div className="sidebar-brand">
          <span className="brand-mark">
            <Radar size={20} />
          </span>
          <div className="brand-text">
            <strong>办事雷达</strong>
            <span>TaskRadar AI</span>
          </div>
          <button type="button" className="icon-btn sidebar-close" onClick={onClose} aria-label="关闭导航">
            <X size={18} />
          </button>
        </div>

        <p className="sidebar-label">工作台</p>
        <nav className="sidebar-nav" aria-label="主导航">
          {navItems.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              type="button"
              className={`nav-item ${current === key ? 'active' : ''}`.trim()}
              aria-current={current === key ? 'page' : undefined}
              onClick={() => onNavigate(key)}
            >
              <Icon size={18} />
              <span>{label}</span>
              {key === 'analyze' && <span className="nav-tag">AI + OCR</span>}
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-note">
            <strong>第五阶段 · 参赛版本</strong>
            <p>演示数据与正式数据已隔离，可一键初始化与清理。</p>
          </div>
          <span className="sidebar-version">
            v{APP_VERSION} · {APP_STAGE}
          </span>
        </div>
      </aside>
    </>
  )
}
