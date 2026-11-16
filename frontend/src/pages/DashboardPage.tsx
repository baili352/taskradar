import { useCallback, useEffect, useState } from 'react'
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock3,
  FileText,
  FlaskConical,
  ListChecks,
  RefreshCw,
  Server,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import { fetchDashboardSummary } from '../api/dashboard'
import { fetchDemoStatus, seedDemoData } from '../api/demo'
import { refreshRisks, riskErrorMessage } from '../api/risks'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card, SectionCard } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { useSystemHealth } from '../hooks/useSystemHealth'
import type { RouteKey } from '../hooks/useHashRoute'
import { formatDateTime, formatToday } from '../lib/format'
import { matterStatusMeta, priorityMeta } from '../lib/meta'
import type { DashboardScope, DashboardSummary, DemoStatus } from '../types'

type DashboardPageProps = {
  onNavigate: (key: RouteKey) => void
}

function greeting(): string {
  const hour = new Date().getHours()
  if (hour < 12) return '上午好'
  if (hour < 18) return '下午好'
  return '晚上好'
}

function dueLabel(daysLeft: number | null, overdue: boolean): string {
  if (overdue && daysLeft !== null) return `已逾期 ${Math.abs(daysLeft)} 天`
  if (daysLeft === null) return '日期未知'
  if (daysLeft === 0) return '今天截止'
  return `${daysLeft} 天后截止`
}

export function DashboardPage({ onNavigate }: DashboardPageProps) {
  const { data, error: healthError, loading: healthLoading, checkedAt, refresh } =
    useSystemHealth()
  const [scope, setScope] = useState<DashboardScope>('real')
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [demoStatus, setDemoStatus] = useState<DemoStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [summaryError, setSummaryError] = useState('')
  const [seeding, setSeeding] = useState(false)

  const loadDemoStatus = useCallback(async () => {
    try {
      setDemoStatus(await fetchDemoStatus())
    } catch {
      // 演示数据状态只影响入口提示，失败时不阻断正式数据展示。
    }
  }, [])

  const loadSummary = useCallback(async (nextScope: DashboardScope) => {
    setLoading(true)
    setSummaryError('')
    try {
      // 进入总览时同步一次风险，保证演示数据初始化后立即有真实风险记录。
      try {
        await refreshRisks()
      } catch {
        /* 同步失败时仍展示数据库中的已有风险记录 */
      }
      setSummary(await fetchDashboardSummary(nextScope === 'demo'))
    } catch (reason) {
      setSummaryError(riskErrorMessage(reason, '读取总览数据失败，请确认后端服务是否正常。'))
      setSummary(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadDemoStatus()
  }, [loadDemoStatus])

  useEffect(() => {
    void loadSummary(scope)
  }, [scope, loadSummary])

  const handleSeed = async () => {
    setSeeding(true)
    try {
      await seedDemoData()
      await loadDemoStatus()
      await loadSummary('demo')
    } catch (reason) {
      setSummaryError(riskErrorMessage(reason, '初始化演示数据失败，请稍后重试。'))
    } finally {
      setSeeding(false)
    }
  }

  const matters = summary?.matters
  const tasks = summary?.tasks
  const materials = summary?.materials
  const risks = summary?.risks
  const isDemo = scope === 'demo'
  const noDemoData = isDemo && demoStatus !== null && !demoStatus.seeded
  const emptyRealData =
    !isDemo && summary !== null && matters?.total === 0 && tasks?.total === 0

  const statCards = [
    {
      key: 'matters',
      label: '待办事项',
      value: (matters?.pending ?? 0) + (matters?.in_progress ?? 0),
      unit: '个',
      hint: `待开始 ${matters?.pending ?? 0} · 进行中 ${matters?.in_progress ?? 0}`,
      icon: ListChecks,
      tone: 'blue',
      target: 'matters' as RouteKey,
    },
    {
      key: 'tasks',
      label: '未完成任务',
      value: tasks?.unfinished ?? 0,
      unit: '个',
      hint: `共 ${tasks?.total ?? 0} 个任务，已完成 ${tasks?.done ?? 0} 个`,
      icon: CheckCircle2,
      tone: 'slate',
      target: 'tasks' as RouteKey,
    },
    {
      key: 'risks',
      label: '未解决风险',
      value: risks?.unresolved ?? 0,
      unit: '条',
      hint: `高 ${risks?.high ?? 0} · 中 ${risks?.medium ?? 0} · 低 ${risks?.low ?? 0}`,
      icon: AlertTriangle,
      tone: 'red',
      target: 'risks' as RouteKey,
    },
    {
      key: 'overdue',
      label: '已逾期任务',
      value: tasks?.overdue ?? 0,
      unit: '个',
      hint: '有明确截止日期且已过期',
      icon: Clock3,
      tone: 'red',
      target: 'tasks' as RouteKey,
    },
    {
      key: 'due3',
      label: '3 天内截止',
      value: tasks?.due_soon_3d ?? 0,
      unit: '个',
      hint: `7 天内共 ${tasks?.due_soon_7d ?? 0} 个`,
      icon: Clock3,
      tone: 'amber',
      target: 'tasks' as RouteKey,
    },
    {
      key: 'materials',
      label: '待核验材料',
      value: materials?.pending ?? 0,
      unit: '项',
      hint: `缺失 ${materials?.missing ?? 0} 项 · 冲突 ${materials?.conflict ?? 0} 项`,
      icon: ShieldCheck,
      tone: 'blue',
      target: 'verification' as RouteKey,
    },
  ]

  const isOnline = data?.status === 'ok'

  return (
    <div className="page-stack">
      <PageHeader
        title="总览"
        description="事项、任务、材料核验与风险的实时统计，全部来自本机 SQLite。"
        badge={
          isDemo ? (
            <Badge tone="demo">演示数据</Badge>
          ) : (
            <Badge tone="success">真实数据</Badge>
          )
        }
        actions={
          <div className="scope-switch" role="tablist" aria-label="数据范围">
            <button
              type="button"
              role="tab"
              aria-selected={scope === 'real'}
              className={`scope-option ${scope === 'real' ? 'is-active' : ''}`}
              onClick={() => setScope('real')}
            >
              正式数据
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={scope === 'demo'}
              className={`scope-option ${scope === 'demo' ? 'is-active' : ''}`}
              onClick={() => setScope('demo')}
            >
              <FlaskConical size={14} />
              演示数据
            </button>
          </div>
        }
      />

      {isDemo && (
        <div className="demo-banner" role="status">
          <FlaskConical size={18} />
          <div>
            <strong>当前展示的是参赛演示数据</strong>
            <p>
              三个演示事项（活动、竞赛、招聘）仅用于展示完整流程，不是真实用户数据，
              也不代表实际使用效果。清理演示数据不会影响正式记录。
            </p>
          </div>
          <Button variant="secondary" size="sm" onClick={() => onNavigate('settings')}>
            管理演示数据
            <ArrowRight size={14} />
          </Button>
        </div>
      )}

      <section className="welcome-card card">
        <div className="welcome-text">
          <span className="welcome-date">{formatToday()}</span>
          <h2>
            {greeting()}
            {isDemo ? '，这是演示视角' : '，体验用户'}
          </h2>
          <p>
            {loading
              ? '正在读取统计数据…'
              : summaryError
                ? '统计数据读取失败，请查看下方错误提示后重试。'
                : `当前 ${risks?.unresolved ?? 0} 条未解决风险：高 ${risks?.high ?? 0} 条、中 ${
                    risks?.medium ?? 0
                  } 条；未完成任务 ${tasks?.unfinished ?? 0} 个，其中已逾期 ${
                    tasks?.overdue ?? 0
                  } 个。`}
          </p>
        </div>
        <div className="welcome-actions">
          <Button variant="accent" onClick={() => onNavigate('analyze')}>
            <Sparkles size={16} />
            从通知提取事项
          </Button>
          <Button variant="secondary" onClick={() => onNavigate('tasks')}>
            <ListChecks size={16} />
            查看任务中心
          </Button>
        </div>
      </section>

      {summaryError && (
        <div className="inline-error" role="alert">
          <AlertCircle size={15} />
          <span>{summaryError}</span>
          <Button variant="ghost" size="sm" onClick={() => void loadSummary(scope)}>
            重试
          </Button>
        </div>
      )}

      {noDemoData ? (
        <div className="empty-state empty-state-card">
          <FlaskConical size={26} />
          <strong>还没有演示数据</strong>
          <p>演示数据包含活动、竞赛、招聘三份通知及其事项、任务、材料和风险，与正式数据完全隔离。</p>
          <div className="empty-actions">
            <Button variant="primary" onClick={() => void handleSeed()} disabled={seeding}>
              {seeding ? '正在初始化…' : '一键初始化演示数据'}
            </Button>
            <Button variant="secondary" onClick={() => setScope('real')}>
              返回正式数据
            </Button>
          </div>
        </div>
      ) : emptyRealData ? (
        <div className="empty-state empty-state-card">
          <Sparkles size={26} />
          <strong>还没有正式数据</strong>
          <p>从一份通知开始：上传文档或图片后由 AI 与本地规则提取事项，再生成任务与材料清单。</p>
          <div className="empty-actions">
            <Button variant="primary" onClick={() => onNavigate('analyze')}>
              <Sparkles size={16} />
              智能分析
            </Button>
            <Button variant="secondary" onClick={() => onNavigate('matters')}>
              手动新建事项
            </Button>
          </div>
        </div>
      ) : (
        <>
          <div className="stat-grid">
            {statCards.map((stat) => {
              const Icon = stat.icon
              return (
                <button
                  type="button"
                  className="stat-card card stat-card-link"
                  key={stat.key}
                  onClick={() => onNavigate(stat.target)}
                  disabled={loading}
                >
                  <div className="stat-top">
                    <span className={`stat-icon tone-${stat.tone}`}>
                      <Icon size={18} />
                    </span>
                    <span className="stat-label">{stat.label}</span>
                    <ArrowRight size={14} className="stat-arrow" />
                  </div>
                  <p className="stat-value">
                    {loading ? '—' : stat.value}
                    <span>{stat.unit}</span>
                  </p>
                  <p className="stat-hint">{stat.hint}</p>
                </button>
              )
            })}
          </div>

          <div className="dashboard-columns">
            <div className="stack">
              <SectionCard
                title="材料核验进度"
                description="已提供 = 已上传文件；已确认 = 规则核验或人工确认通过"
                action={
                  <>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => void loadSummary(scope)}
                      disabled={loading}
                    >
                      <RefreshCw size={14} className={loading ? 'spin' : undefined} />
                      刷新
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => onNavigate('verification')}>
                      进入材料核验
                      <ArrowRight size={14} />
                    </Button>
                  </>
                }
              >
                {loading ? (
                  <p className="muted-note">正在读取材料统计…</p>
                ) : (materials?.total ?? 0) === 0 ? (
                  <div className="empty-state">
                    <FileText size={22} />
                    <strong>还没有材料清单</strong>
                    <p>在事项详情中生成材料清单后，这里会显示准备与核验进度。</p>
                    <Button variant="secondary" size="sm" onClick={() => onNavigate('matters')}>
                      前往事项
                    </Button>
                  </div>
                ) : (
                  <div className="progress-block">
                    <div className="progress-row">
                      <div className="progress-head">
                        <span>材料准备</span>
                        <strong>{materials?.prepared_percent ?? 0}%</strong>
                      </div>
                      <div className="progress-track">
                        <span
                          className="progress-fill fill-blue"
                          style={{ width: `${materials?.prepared_percent ?? 0}%` }}
                        />
                      </div>
                      <small>
                        已提供 {materials?.provided ?? 0} / {materials?.total ?? 0} 项，缺失{' '}
                        {materials?.missing ?? 0} 项
                      </small>
                    </div>
                    <div className="progress-row">
                      <div className="progress-head">
                        <span>核验确认</span>
                        <strong>{materials?.verified_percent ?? 0}%</strong>
                      </div>
                      <div className="progress-track">
                        <span
                          className="progress-fill fill-green"
                          style={{ width: `${materials?.verified_percent ?? 0}%` }}
                        />
                      </div>
                      <small>
                        已确认 {materials?.qualified ?? 0} 项，待核验 {materials?.pending ?? 0} 项，
                        冲突 {materials?.conflict ?? 0} 项，无法判断 {materials?.uncertain ?? 0} 项
                      </small>
                    </div>
                  </div>
                )}
              </SectionCard>

              <SectionCard
                title="近期截止任务"
                description="按截止时间排序，含已逾期与 7 天内截止的未完成任务"
                action={
                  <Button variant="ghost" size="sm" onClick={() => onNavigate('tasks')}>
                    查看全部
                    <ArrowRight size={14} />
                  </Button>
                }
              >
                {loading ? (
                  <p className="muted-note">正在读取任务…</p>
                ) : (summary?.due_soon_tasks.length ?? 0) === 0 ? (
                  <div className="empty-state">
                    <CheckCircle2 size={22} />
                    <strong>近期没有临近截止的任务</strong>
                    <p>存在明确截止日期的未完成任务会在这里按时间排序。</p>
                  </div>
                ) : (
                  <div className="recent-list">
                    {summary?.due_soon_tasks.map((task) => {
                      const priority = priorityMeta[task.priority]
                      return (
                        <button
                          type="button"
                          className="recent-row"
                          key={task.id}
                          onClick={() => onNavigate('tasks')}
                        >
                          <span className={`row-icon ${task.overdue ? 'level-high' : ''}`}>
                            <Clock3 size={16} />
                          </span>
                          <span className="recent-main">
                            <strong>{task.title}</strong>
                            <small>{task.matter_name || `事项 #${task.matter_id}`}</small>
                          </span>
                          <span className={`recent-deadline ${task.overdue ? 'text-danger' : ''}`}>
                            <small>{dueLabel(task.days_left, task.overdue)}</small>
                          </span>
                          <Badge tone={priority.tone}>{priority.label}</Badge>
                        </button>
                      )
                    })}
                  </div>
                )}
              </SectionCard>

              <SectionCard
                title="最近处理的事项"
                description="按最后更新时间排序"
                action={
                  <Button variant="ghost" size="sm" onClick={() => onNavigate('matters')}>
                    查看全部
                    <ArrowRight size={14} />
                  </Button>
                }
              >
                {loading ? (
                  <p className="muted-note">正在读取事项…</p>
                ) : (summary?.recent_matters.length ?? 0) === 0 ? (
                  <div className="empty-state">
                    <FileText size={22} />
                    <strong>还没有事项</strong>
                    <p>前往「智能分析」上传通知，或在「我的事项」手动新建。</p>
                  </div>
                ) : (
                  <div className="recent-list">
                    {summary?.recent_matters.map((matter) => {
                      const status = matterStatusMeta[matter.status]
                      return (
                        <button
                          type="button"
                          className="recent-row"
                          key={matter.id}
                          onClick={() => onNavigate('matters')}
                        >
                          <span className="row-icon">
                            <FileText size={16} />
                          </span>
                          <span className="recent-main">
                            <strong>{matter.name}</strong>
                            <small>
                              {matter.matter_type || '未分类'} · 更新于{' '}
                              {formatDateTime(matter.updated_at)}
                            </small>
                          </span>
                          <span className="recent-deadline">
                            <small>{matter.deadline ?? '未设置截止日期'}</small>
                          </span>
                          <Badge tone={status.tone}>{status.label}</Badge>
                        </button>
                      )
                    })}
                  </div>
                )}
              </SectionCard>
            </div>

            <div className="stack">
              <SectionCard
                title="系统运行状态"
                description="来自后端 /api/health 的实时检测结果"
                action={
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => void refresh()}
                    disabled={healthLoading}
                  >
                    <RefreshCw size={14} className={healthLoading ? 'spin' : undefined} />
                    重新检测
                  </Button>
                }
              >
                <div className="status-list">
                  <div className="status-row">
                    <span>后端服务</span>
                    <strong className={isOnline ? 'text-success' : 'text-danger'}>
                      {healthLoading ? '检测中…' : isOnline ? '已连接' : '未连接'}
                    </strong>
                  </div>
                  <div className="status-row">
                    <span>数据库</span>
                    <strong className={data?.database === 'ok' ? 'text-success' : 'text-muted'}>
                      {data?.database === 'ok' ? 'SQLite 正常' : '—'}
                    </strong>
                  </div>
                  <div className="status-row">
                    <span>运行环境</span>
                    <strong>{data?.environment ?? '—'}</strong>
                  </div>
                  <div className="status-row">
                    <span>服务版本</span>
                    <strong>{data?.version ?? '—'}</strong>
                  </div>
                </div>
                {healthError && (
                  <p className="inline-error">
                    {healthError}。请确认后端服务已启动，再点击「重新检测」。
                  </p>
                )}
                <p className="muted-note">最后检测：{checkedAt ?? '—'}</p>
              </SectionCard>

              <Card className="info-panel">
                <span className="info-panel-icon">
                  <Server size={18} />
                </span>
                <div>
                  <strong>统计口径</strong>
                  <p>
                    总览只汇总数据库中的真实记录：任务逾期依据明确截止日期判断，材料进度依据上传与核验状态计算，
                    风险数量来自已同步的风险记录。演示数据会在页面上明确标记，不参与正式统计。
                  </p>
                </div>
              </Card>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
