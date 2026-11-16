import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock3,
  FileText,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react'
import { isRequestCancelled } from '../api/client'
import {
  fetchMatterRisks,
  fetchRisk,
  fetchRiskSummary,
  fetchRisks,
  markRiskRead,
  refreshRisks,
  riskErrorMessage,
} from '../api/risks'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card, SectionCard } from '../components/ui/Card'
import { Modal } from '../components/ui/Modal'
import { PageHeader } from '../components/ui/PageHeader'
import { useToast } from '../components/ui/Toast'
import type { RouteKey } from '../hooks/useHashRoute'
import { formatDateTime, formatFileSize } from '../lib/format'
import {
  deadlineSourceMeta,
  riskLevelMeta,
  riskStatusMeta,
  riskTypeMeta,
} from '../lib/meta'
import type {
  MatterRiskSummary,
  RiskLevel,
  RiskRecord,
  RiskStatusFilter,
  RiskSummary,
  RiskType,
} from '../types'

const statusFilters: { value: RiskStatusFilter; label: string }[] = [
  { value: 'unresolved', label: '未解决' },
  { value: 'active', label: '待处理' },
  { value: 'read', label: '已读' },
  { value: 'resolved', label: '已解决' },
  { value: 'all', label: '全部' },
]

const levelFilters: { value: 'all' | RiskLevel; label: string }[] = [
  { value: 'all', label: '全部等级' },
  { value: 'high', label: '高风险' },
  { value: 'medium', label: '中风险' },
  { value: 'low', label: '低风险' },
]

const riskImpact: Partial<Record<RiskType, string>> = {
  overdue: '相关任务已超过截止日期，继续拖延可能导致事项无法按期办理或资格失效。',
  due_soon: '距离截止时间不足，若未及时完成，任务可能转为逾期并影响整个事项进度。',
  backlog: '存在多项未完成任务，事项推进存在积压，临近截止时容易集中逾期。',
  material_missing: '必备材料尚未提供，材料清单不完整，办理可能被退回或无法继续。',
  material_pending: '材料已上传但尚未核验，目前无法确认是否符合要求。',
  material_incomplete: '材料内容不完整，可能被要求补正，影响受理进度。',
  material_conflict: '材料之间存在不一致，可能影响资格审核或受理结果。',
  material_uncertain: '规则核验无法确认材料是否符合要求，需要人工对照原文核实。',
}

const dataSourceLabels: Record<string, string> = {
  'tasks.deadline': '任务截止日期',
  'tasks.deadline_source': '任务截止日期来源',
  'tasks.status': '任务状态',
  'tasks.title': '任务名称',
  'matters.deadline': '事项截止日期',
  'matters.deadline_source': '事项截止日期来源',
  'materials.status': '材料状态',
  'materials.verification_evidence_json': '材料核验记录',
}

const materialCheckTone = {
  pass: 'success',
  warn: 'warning',
  unknown: 'neutral',
} as const

function daysText(days: number | null | undefined): string {
  if (days === null || days === undefined) return '—'
  if (days < 0) return `已逾期 ${Math.abs(days)} 天`
  if (days === 0) return '今天截止'
  return `${days} 天后截止`
}

type RisksPageProps = {
  onNavigate: (key: RouteKey, params?: Record<string, string>) => void
}

export function RisksPage({ onNavigate }: RisksPageProps) {
  const [summary, setSummary] = useState<RiskSummary | null>(null)
  const [risks, setRisks] = useState<RiskRecord[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [refreshing, setRefreshing] = useState(false)

  const [riskType, setRiskType] = useState<'all' | RiskType>('all')
  const [level, setLevel] = useState<'all' | RiskLevel>('all')
  const [status, setStatus] = useState<RiskStatusFilter>('unresolved')

  const [detail, setDetail] = useState<RiskRecord | null>(null)
  const [matterSummary, setMatterSummary] = useState<MatterRiskSummary | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')
  const [markingId, setMarkingId] = useState<number | null>(null)

  const { showToast } = useToast()
  // 进入风险中心时只同步一次；后续筛选、打开详情都只读取数据库。
  const initialSyncDone = useRef(false)
  const mountedRef = useRef(true)
  const listSequence = useRef(0)
  const detailSequence = useRef(0)
  const listControllerRef = useRef<AbortController | null>(null)
  const detailControllerRef = useRef<AbortController | null>(null)
  const refreshControllerRef = useRef<AbortController | null>(null)
  const markReadControllerRef = useRef<AbortController | null>(null)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      listSequence.current += 1
      detailSequence.current += 1
      listControllerRef.current?.abort()
      detailControllerRef.current?.abort()
      refreshControllerRef.current?.abort()
      markReadControllerRef.current?.abort()
    }
  }, [])

  const loadRisks = useCallback(async () => {
    if (!mountedRef.current) return
    listControllerRef.current?.abort()
    const controller = new AbortController()
    const requestId = ++listSequence.current
    listControllerRef.current = controller
    setLoading(true)
    setLoadError('')
    try {
      const [summaryData, listData] = await Promise.all([
        fetchRiskSummary(controller.signal),
        fetchRisks(
          {
            riskType: riskType === 'all' ? undefined : riskType,
            level: level === 'all' ? undefined : level,
            status,
            limit: 100,
          },
          controller.signal,
        ),
      ])
      if (!mountedRef.current || requestId !== listSequence.current) return
      setSummary(summaryData)
      setRisks(listData.items)
      setTotal(listData.total)
    } catch (reason) {
      if (
        isRequestCancelled(reason) ||
        !mountedRef.current ||
        requestId !== listSequence.current
      ) {
        return
      }
      setLoadError(riskErrorMessage(reason, '读取风险提醒失败，请确认后端服务是否正常。'))
    } finally {
      if (mountedRef.current && requestId === listSequence.current) {
        setLoading(false)
      }
    }
  }, [riskType, level, status])

  useEffect(() => {
    const controller = new AbortController()
    const run = async () => {
      if (!initialSyncDone.current) {
        initialSyncDone.current = true
        try {
          // 显式 POST 触发同步；失败时仍读取已有记录，不阻断页面。
          await refreshRisks(controller.signal)
        } catch {
          /* 同步失败不阻断读取，用户可点击「重新分析」重试 */
        }
      }
      if (!controller.signal.aborted) await loadRisks()
    }
    void run()
    return () => controller.abort()
  }, [loadRisks])

  const handleRefresh = async () => {
    if (refreshing || !mountedRef.current) return
    const controller = new AbortController()
    refreshControllerRef.current = controller
    setRefreshing(true)
    try {
      const result = await refreshRisks(controller.signal)
      if (controller.signal.aborted) return
      await loadRisks()
      if (!mountedRef.current || controller.signal.aborted) return
      const parts = [`新增 ${result.created}`, `更新 ${result.updated}`, `解决 ${result.resolved}`]
      if (result.revived > 0) parts.push(`恢复 ${result.revived}`)
      showToast(`风险已重新分析：${parts.join('，')}。`, 'success')
    } catch (reason) {
      if (isRequestCancelled(reason) || !mountedRef.current) return
      showToast(riskErrorMessage(reason, '重新分析风险失败，请稍后重试。'), 'warning')
    } finally {
      if (mountedRef.current) setRefreshing(false)
    }
  }

  const openDetail = async (risk: RiskRecord) => {
    if (!mountedRef.current) return
    detailControllerRef.current?.abort()
    const controller = new AbortController()
    const requestId = ++detailSequence.current
    detailControllerRef.current = controller
    setDetail(risk)
    setDetailLoading(true)
    setDetailError('')
    setMatterSummary(null)
    try {
      const [detailData, matterData] = await Promise.all([
        fetchRisk(risk.id, controller.signal),
        fetchMatterRisks(risk.matter_id, controller.signal),
      ])
      if (!mountedRef.current || requestId !== detailSequence.current) return
      setDetail(detailData)
      setMatterSummary(matterData.summary)
    } catch (reason) {
      const cancelled = isRequestCancelled(reason)
      controller.abort()
      if (
        cancelled ||
        !mountedRef.current ||
        requestId !== detailSequence.current
      ) {
        return
      }
      setDetailError(riskErrorMessage(reason, '读取风险详情失败，请稍后重试。'))
    } finally {
      if (mountedRef.current && requestId === detailSequence.current) {
        setDetailLoading(false)
      }
    }
  }

  const closeDetail = () => {
    detailSequence.current += 1
    detailControllerRef.current?.abort()
    setDetail(null)
    setDetailLoading(false)
    setDetailError('')
    setMatterSummary(null)
  }

  const handleMarkRead = async (risk: RiskRecord) => {
    if (markingId !== null || !mountedRef.current) return
    const controller = new AbortController()
    markReadControllerRef.current = controller
    setMarkingId(risk.id)
    try {
      const updated = await markRiskRead(risk.id, controller.signal)
      if (!mountedRef.current || controller.signal.aborted) return
      setRisks((current) => current.map((item) => (item.id === updated.id ? updated : item)))
      setDetail((current) => (current && current.id === updated.id ? updated : current))
      showToast(`风险 #${risk.id} 已标记为已读。`, 'success')
      await loadRisks()
    } catch (reason) {
      if (isRequestCancelled(reason) || !mountedRef.current) return
      showToast(riskErrorMessage(reason, '标记已读失败，请稍后重试。'), 'warning')
    } finally {
      if (mountedRef.current) setMarkingId(null)
    }
  }

  const typeOptions = useMemo(
    () => (Object.keys(riskTypeMeta) as RiskType[]).map((key) => ({ key, ...riskTypeMeta[key] })),
    [],
  )

  const evidence = detail?.evidence ?? null
  const unfinished = evidence?.unfinished_tasks ?? []
  const material = evidence?.material ?? null
  const checkList = material?.verification?.checks ?? []

  return (
    <div className="page-stack">
      <PageHeader
        title="风险提醒中心"
        description="基于真实事项、任务与材料数据，按统一规则识别逾期、截止与材料风险。"
        badge={<Badge tone="success">本机数据</Badge>}
        actions={
          <>
            <Button variant="secondary" onClick={() => void loadRisks()} disabled={loading}>
              <RefreshCw size={16} className={loading ? 'spin' : undefined} />
              刷新
            </Button>
            <Button variant="primary" onClick={() => void handleRefresh()} disabled={refreshing}>
              <ShieldCheck size={16} />
              {refreshing ? '分析中…' : '重新分析'}
            </Button>
          </>
        }
      />

      <div className="risk-summary-grid">
        <Card className="risk-summary-card level-high">
          <span className="risk-summary-icon">
            <AlertTriangle size={18} />
          </span>
          <div>
            <p className="risk-summary-label">高风险</p>
            <strong>{summary?.high ?? 0}</strong>
          </div>
        </Card>
        <Card className="risk-summary-card level-medium">
          <span className="risk-summary-icon">
            <AlertCircle size={18} />
          </span>
          <div>
            <p className="risk-summary-label">中风险</p>
            <strong>{summary?.medium ?? 0}</strong>
          </div>
        </Card>
        <Card className="risk-summary-card level-low">
          <span className="risk-summary-icon">
            <Clock3 size={18} />
          </span>
          <div>
            <p className="risk-summary-label">低风险</p>
            <strong>{summary?.low ?? 0}</strong>
          </div>
        </Card>
        <Card className="risk-summary-card level-resolved">
          <span className="risk-summary-icon">
            <CheckCircle2 size={18} />
          </span>
          <div>
            <p className="risk-summary-label">已解决</p>
            <strong>{summary?.resolved ?? 0}</strong>
          </div>
        </Card>
      </div>

      <p className="risk-meta-note">
        统计时区：{summary?.timezone ?? 'Asia/Shanghai'} · 今天：{summary?.today ?? '—'} · 未解决{' '}
        {summary?.total_unresolved ?? 0} 条，其中待处理 {summary?.active ?? 0} 条、已读{' '}
        {summary?.read ?? 0} 条。
      </p>

      <SectionCard
        title="风险列表"
        description={`当前筛选结果 ${total} 条；已解决风险保留历史记录，可切换状态查看。`}
      >
        <div className="risk-toolbar">
          <label className="field risk-filter-field">
            <span>风险类型</span>
            <select
              className="select"
              value={riskType}
              onChange={(event) => setRiskType(event.target.value as 'all' | RiskType)}
            >
              <option value="all">全部类型</option>
              {typeOptions.map((item) => (
                <option key={item.key} value={item.key}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <div className="filter-group" role="group" aria-label="按风险等级筛选">
            {levelFilters.map((item) => (
              <button
                key={item.value}
                type="button"
                className={`filter-chip ${level === item.value ? 'active' : ''}`.trim()}
                onClick={() => setLevel(item.value)}
              >
                {item.label}
              </button>
            ))}
          </div>
          <div className="filter-group" role="group" aria-label="按风险状态筛选">
            {statusFilters.map((item) => (
              <button
                key={item.value}
                type="button"
                className={`filter-chip ${status === item.value ? 'active' : ''}`.trim()}
                onClick={() => setStatus(item.value)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>

        {loadError && (
          <div className="inline-error" role="alert">
            <AlertCircle size={15} />
            <span>{loadError}</span>
          </div>
        )}

        {loading ? (
          <p className="muted-note">正在读取风险提醒…</p>
        ) : risks.length === 0 ? (
          <div className="empty-state">
            <CheckCircle2 size={22} />
            <strong>当前筛选下没有风险提醒</strong>
            <p>截止日期正常、任务已完成或材料已确认符合时，不会产生提醒。</p>
          </div>
        ) : (
          <ul className="risk-list">
            {risks.map((risk) => {
              const levelInfo = riskLevelMeta[risk.risk_level]
              const statusInfo = riskStatusMeta[risk.status]
              return (
                <li
                  className={`risk-row level-${risk.risk_level} ${risk.status === 'active' ? 'unread' : ''}`.trim()}
                  key={risk.id}
                >
                  <span className="risk-level-bar" aria-hidden="true" />
                  <button type="button" className="risk-row-main" onClick={() => void openDetail(risk)}>
                    <span className="risk-row-head">
                      <strong>{risk.title}</strong>
                      {risk.is_demo && <Badge tone="demo">演示数据</Badge>}
                      <Badge tone={levelInfo.tone}>{levelInfo.label}</Badge>
                      <Badge tone={statusInfo.tone}>{statusInfo.label}</Badge>
                      {risk.status === 'active' && <span className="risk-dot" aria-label="未读" />}
                    </span>
                    <small className="risk-row-meta">
                      {riskTypeMeta[risk.risk_type].label} · 事项「{risk.matter_name || `#${risk.matter_id}`}」
                      {risk.task_id ? ` · 任务 #${risk.task_id}` : ''}
                      {risk.material_id ? ` · 材料 #${risk.material_id}` : ''} · 最近发现{' '}
                      {formatDateTime(risk.last_seen_at)}
                    </small>
                    <p className="risk-row-desc">{risk.description}</p>
                  </button>
                  <div className="risk-row-actions">
                    {risk.status === 'active' && (
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => void handleMarkRead(risk)}
                        disabled={markingId !== null}
                      >
                        {markingId === risk.id ? '处理中…' : '标记已读'}
                      </Button>
                    )}
                    <Button variant="ghost" size="sm" onClick={() => void openDetail(risk)}>
                      查看详情
                      <ArrowRight size={14} />
                    </Button>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </SectionCard>

      <Modal
        open={detail !== null}
        title={detail ? detail.title : '风险详情'}
        description="展示风险判断原因、影响与下一步操作；记录来自本机数据库，演示数据单独标记。"
        onClose={closeDetail}
        footer={
          <>
            <Button variant="secondary" onClick={closeDetail}>
              关闭
            </Button>
            {detail && detail.status === 'active' && (
              <Button
                variant="primary"
                onClick={() => void handleMarkRead(detail)}
                disabled={markingId !== null}
              >
                标记已读
              </Button>
            )}
          </>
        }
      >
        {detailLoading && <p className="muted-note">正在读取风险详情…</p>}
        {detailError && (
          <div className="inline-error" role="alert">
            <AlertCircle size={15} />
            <span>{detailError}</span>
          </div>
        )}
        {detail && (
          <div className="risk-detail">
            <div className="risk-detail-badges">
              <Badge tone={riskLevelMeta[detail.risk_level].tone}>
                {riskLevelMeta[detail.risk_level].label}
              </Badge>
              <Badge tone={riskStatusMeta[detail.status].tone}>
                {riskStatusMeta[detail.status].label}
              </Badge>
              <Badge tone="neutral">{riskTypeMeta[detail.risk_type].label}</Badge>
              {detail.is_demo && <Badge tone="demo">演示数据</Badge>}
              <Badge tone="info">#{detail.id}</Badge>
            </div>

            <div className="risk-explain">
              <div className="risk-explain-block">
                <span className="risk-explain-label">为什么出现</span>
                <p>{evidence?.rule || detail.description}</p>
                {evidence?.note && <p className="muted-note">补充说明：{evidence.note}</p>}
              </div>
              <div className="risk-explain-block">
                <span className="risk-explain-label">影响什么</span>
                <p>{riskImpact[detail.risk_type] ?? detail.description}</p>
              </div>
              <div className="risk-explain-block">
                <span className="risk-explain-label">下一步做什么</span>
                <p>{detail.suggestion || '请人工核查该风险，并补充对应材料或任务。'}</p>
              </div>
            </div>

            <p className="risk-detail-desc">{detail.description}</p>

            <div className="risk-detail-grid">
              <div>
                <span>关联事项</span>
                <strong>{detail.matter_name || `事项 #${detail.matter_id}`}</strong>
              </div>
              <div>
                <span>关联任务</span>
                <strong>{detail.task_title ?? '—'}</strong>
              </div>
              <div>
                <span>关联材料</span>
                <strong>{detail.material_name ?? '—'}</strong>
              </div>
              <div>
                <span>最近发现</span>
                <strong>{formatDateTime(detail.last_seen_at)}</strong>
              </div>
              <div>
                <span>首次发现</span>
                <strong>{formatDateTime(detail.first_seen_at)}</strong>
              </div>
              <div>
                <span>已读时间</span>
                <strong>{formatDateTime(detail.read_at)}</strong>
              </div>
            </div>

            <div className="risk-detail-block">
              <h4>数据来源</h4>
              <ul className="risk-source-list">
                {(evidence?.data_sources ?? []).map((source) => (
                  <li key={source}>{dataSourceLabels[source] ?? source}</li>
                ))}
              </ul>
              <p className="muted-note">
                统计时区 {evidence?.timezone ?? summary?.timezone ?? 'Asia/Shanghai'} · 今天{' '}
                {evidence?.today ?? summary?.today ?? '—'}
              </p>
            </div>

            {evidence?.deadline_raw && (
              <div className="risk-detail-block">
                <h4>截止日期依据</h4>
                <div className="risk-detail-grid">
                  <div>
                    <span>原文日期</span>
                    <strong>{evidence.deadline_raw}</strong>
                  </div>
                  <div>
                    <span>归一化日期</span>
                    <strong>{evidence.deadline_normalized ?? '待核实'}</strong>
                  </div>
                  <div>
                    <span>日期来源</span>
                    <strong>{deadlineSourceMeta[evidence.deadline_source ?? 'none']}</strong>
                  </div>
                  <div>
                    <span>剩余时间</span>
                    <strong>{daysText(evidence.days_left)}</strong>
                  </div>
                </div>
              </div>
            )}

            {unfinished.length > 0 && (
              <div className="risk-detail-block">
                <h4>未完成任务（{unfinished.length}）</h4>
                <ul className="risk-task-list">
                  {unfinished.map((task) => (
                    <li key={task.id}>
                      <div>
                        <strong>{task.title}</strong>
                        <small>
                          #{task.id} · {task.deadline ?? '未设置截止时间'} ·{' '}
                          {daysText(task.days_left)}
                        </small>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() =>
                          onNavigate('tasks', {
                            matter: String(detail.matter_id),
                            task: String(task.id),
                          })
                        }
                      >
                        查看任务
                        <ArrowRight size={14} />
                      </Button>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {material && (
              <div className="risk-detail-block">
                <h4>材料信息</h4>
                <div className="risk-detail-grid">
                  <div>
                    <span>材料名称</span>
                    <strong>{material.name}</strong>
                  </div>
                  <div>
                    <span>材料状态</span>
                    <strong>{material.status}</strong>
                  </div>
                  <div>
                    <span>文件</span>
                    <strong>{material.original_filename ?? '未上传'}</strong>
                  </div>
                  <div>
                    <span>文件大小</span>
                    <strong>
                      {material.file_size ? formatFileSize(material.file_size) : '—'}
                    </strong>
                  </div>
                </div>
                {material.description && (
                  <p className="muted-note">材料要求：{material.description}</p>
                )}
                {material.requirement_evidence && (
                  <p className="evidence-line">
                    要求来源：{material.requirement_evidence.location} ·「
                    {material.requirement_evidence.text}」
                  </p>
                )}
                {material.verification && (
                  <div className="risk-verify-box">
                    <p>
                      <strong>核验结论：</strong>
                      {material.verification.summary}
                    </p>
                    <p className="muted-note">
                      核验方式：
                      {material.verification.source === 'rule' ? '规则核验' : '人工确认'} ·{' '}
                      {formatDateTime(material.verification.verified_at)}
                    </p>
                    {checkList.length > 0 && (
                      <ul className="risk-check-list">
                        {checkList.map((check) => (
                          <li key={check.key}>
                            <Badge tone={materialCheckTone[check.status]}>{check.label}</Badge>
                            <span>{check.message}</span>
                            {check.excerpt && <em>「{check.excerpt}」</em>}
                          </li>
                        ))}
                      </ul>
                    )}
                    {material.verification.reasons.length > 0 && (
                      <ul className="risk-reason-list">
                        {material.verification.reasons.map((reason) => (
                          <li key={reason}>{reason}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </div>
            )}

            {matterSummary && (
              <div className="risk-detail-block">
                <h4>事项整体风险摘要</h4>
                <p>
                  事项「{matterSummary.matter_name}」：{matterSummary.headline}
                </p>
                <p className="muted-note">
                  整体等级：{riskLevelMeta[matterSummary.level].label} · 未完成任务{' '}
                  {matterSummary.unfinished_tasks} 个 · 材料 {matterSummary.material_total} 项
                  （未提供 {matterSummary.material_missing}、待核验{' '}
                  {matterSummary.material_pending}、冲突 {matterSummary.material_conflict}）
                </p>
              </div>
            )}

            <div className="risk-detail-links">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => onNavigate('matters', { matter: String(detail.matter_id) })}
              >
                <FileText size={14} />
                查看事项
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() =>
                  onNavigate('tasks', {
                    matter: String(detail.matter_id),
                    ...(detail.task_id ? { task: String(detail.task_id) } : {}),
                  })
                }
              >
                <Clock3 size={14} />
                查看任务
              </Button>
              {detail.material_id && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() =>
                    onNavigate('verification', {
                      matter: String(detail.matter_id),
                      material: String(detail.material_id),
                    })
                  }
                >
                  <ShieldCheck size={14} />
                  查看材料
                </Button>
              )}
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
