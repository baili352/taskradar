import {
  AlertTriangle,
  ClipboardList,
  LayoutDashboard,
  ListChecks,
  Settings,
  ShieldCheck,
  Sparkles,
  type LucideIcon,
} from 'lucide-react'
import type { RouteKey } from '../hooks/useHashRoute'

export type NavItem = {
  key: RouteKey
  label: string
  description: string
  icon: LucideIcon
}

export const navItems: NavItem[] = [
  { key: 'dashboard', label: '总览', description: '今日概览与系统状态', icon: LayoutDashboard },
  { key: 'analyze', label: '智能分析', description: '上传材料并查看分析流程', icon: Sparkles },
  { key: 'matters', label: '我的事项', description: '管理全部办事事项', icon: ClipboardList },
  { key: 'verification', label: '材料核验', description: '核对材料齐全情况', icon: ShieldCheck },
  { key: 'tasks', label: '任务中心', description: '跟进任务进度', icon: ListChecks },
  { key: 'risks', label: '风险提醒', description: '逾期、截止与材料风险', icon: AlertTriangle },
  { key: 'settings', label: '设置', description: '产品与系统信息', icon: Settings },
]

export function getNavItem(key: RouteKey): NavItem {
  return navItems.find((item) => item.key === key) ?? navItems[0]
}
