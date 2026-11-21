import { useCallback, useEffect, useState } from 'react'
import {
  AlertCircle,
  Cpu,
  Database,
  ExternalLink,
  FileText,
  FlaskConical,
  Info,
  Lock,
  RefreshCw,
  ShieldCheck,
  Trash2,
} from 'lucide-react'
import { clearDemoData, fetchDemoStatus, refreshDemoData, seedDemoData } from '../api/demo'
import { fetchAnalysisCapabilities, testAIConnection } from '../api/analysis'
import { riskErrorMessage } from '../api/risks'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { SectionCard } from '../components/ui/Card'
import { Modal } from '../components/ui/Modal'
import { PageHeader } from '../components/ui/PageHeader'
import { useToast } from '../components/ui/Toast'
import { useSystemHealth } from '../hooks/useSystemHealth'
import { formatDateTime } from '../lib/format'
import { APP_STAGE, APP_VERSION } from '../lib/version'
import type { AIConnectionTestResult, AnalysisCapabilities, DemoStatus } from '../types'

export function SettingsPage() {
  const { data, error, loading, checkedAt, refresh } = useSystemHealth()
  const { showToast } = useToast()
  const online = data?.status === 'ok'
  const [demoStatus, setDemoStatus] = useState<DemoStatus | null>(null)
  const [demoBusy, setDemoBusy] = useState(false)
  const [demoError, setDemoError] = useState('')
  const [confirmClear, setConfirmClear] = useState(false)
  const [confirmRefresh, setConfirmRefresh] = useState(false)
  const [capabilities, setCapabilities] = useState<AnalysisCapabilities | null>(null)
  const [capabilityError, setCapabilityError] = useState('')
  const [aiTesting, setAiTesting] = useState(false)
  const [aiTestResult, setAiTestResult] = useState<AIConnectionTestResult | null>(null)

  const loadDemoStatus = useCallback(async () => {
    try {
      setDemoStatus(await fetchDemoStatus())
      setDemoError('')
    } catch (reason) {
      setDemoError(riskErrorMessage(reason, '读取演示数据状态失败，请确认后端服务是否正常。'))
    }
  }, [])

  const loadCapabilities = useCallback(async () => {
    try {
      setCapabilities(await fetchAnalysisCapabilities())
      setCapabilityError('')
    } catch (reason) {
      setCapabilityError(riskErrorMessage(reason, '读取 AI 与 OCR 状态失败，请确认后端服务是否正常。'))
    }
  }, [])

  useEffect(() => {
    void loadDemoStatus()
    void loadCapabilities()
  }, [loadDemoStatus, loadCapabilities])

  const handleSeed = async () => {
    setDemoBusy(true)
    setDemoError('')
    try {
      const status = await seedDemoData()
      setDemoStatus(status)
      showToast(
        status.matters > 0 ? '演示数据已初始化，可在总览页切换查看。' : '演示数据已存在。',
        'success',
      )
    } catch (reason) {
      setDemoError(riskErrorMessage(reason, '初始化演示数据失败，请稍后重试。'))
    } finally {
      setDemoBusy(false)
    }
  }

  const handleRefresh = async () => {
    setDemoBusy(true)
    setDemoError('')
    try {
      const status = await refreshDemoData()
      setDemoStatus(status)
      setConfirmRefresh(false)
      showToast('演示数据已按今天重新计算，正式数据未受影响。', 'success')
    } catch (reason) {
      setDemoError(riskErrorMessage(reason, '刷新演示数据失败，请稍后重试。'))
    } finally {
      setDemoBusy(false)
    }
  }

  const handleClear = async () => {
    setDemoBusy(true)
    setDemoError('')
    try {
      const status = await clearDemoData()
      setDemoStatus(status)
      setConfirmClear(false)
      showToast('演示数据已清理，正式数据未受影响。', 'success')
    } catch (reason) {
      setDemoError(riskErrorMessage(reason, '清理演示数据失败，请稍后重试。'))
    } finally {
      setDemoBusy(false)
    }
  }

  const handleTestAI = async () => {
    if (aiTesting) return
    setAiTesting(true)
    setAiTestResult(null)
    try {
      setAiTestResult(await testAIConnection())
    } catch (reason) {
      setAiTestResult({
        success: false,
        message: riskErrorMessage(reason, '连接测试失败，请稍后重试。'),
        model: capabilities?.ai_model ?? '',
        elapsed_ms: 0,
      })
    } finally {
      setAiTesting(false)
    }
  }

  const productInfo = [
    { label: '产品名称', value: '办事雷达 TaskRadar AI' },
    { label: '产品定位', value: 'AI 智能事项拆解、本地 OCR 与材料规则核验平台' },
    { label: '当前版本', value: `${APP_VERSION}（${APP_STAGE}）` },
    { label: '技术架构', value: 'React + TypeScript + Vite / FastAPI + SQLite' },
    {
      label: '数据状态',
      value: '事项、任务、材料与风险记录均保存在本机 SQLite，刷新或重启后仍然存在',
    },
  ]

  return (
    <div className="page-stack">
      <PageHeader
        title="设置"
        description="查看产品信息、本地数据存储方式与系统运行状态。"
        badge={<Badge tone="success">本机运行</Badge>}
      />

      <div className="settings-grid">
        <div className="stack">
          <SectionCard title="产品信息" description="当前产品的定位与版本">
            <dl className="kv-list">
              {productInfo.map((item) => (
                <div className="kv-row" key={item.label}>
                  <dt>{item.label}</dt>
                  <dd>{item.value}</dd>
                </div>
              ))}
            </dl>
          </SectionCard>

          <SectionCard
            title="AI 模型与本地 OCR"
            description="密钥只在 backend/.env 或环境变量中配置，修改后重启后端"
            action={
              <Button variant="ghost" size="sm" onClick={() => void loadCapabilities()}>
                <RefreshCw size={14} />
                刷新状态
              </Button>
            }
          >
            <div className="setting-row">
              <div className="setting-info">
                <span className="setting-icon"><Cpu size={17} /></span>
                <div>
                  <strong>{capabilities?.ai_provider ?? '正在读取模型服务商…'}</strong>
                  <p>模型：{capabilities?.ai_model || '未设置'}。智能分析使用 OpenAI 兼容接口，证据仍由本地原文生成。</p>
                </div>
              </div>
              <div className="setting-action">
                <Badge tone={capabilities?.ai_configured ? 'success' : 'neutral'}>
                  {capabilities?.ai_configured ? '已配置' : '未完整配置'}
                </Badge>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => void handleTestAI()}
                  disabled={aiTesting || !capabilities?.ai_configured}
                >
                  {aiTesting ? '测试中…' : '测试连接'}
                </Button>
              </div>
            </div>

            <div className="setting-row">
              <div className="setting-info">
                <span className="setting-icon"><Lock size={17} /></span>
                <div>
                  <strong>API 密钥</strong>
                  <p>仅显示配置状态，不读取或展示密钥值。Ollama 等本地服务可留空，云端服务可在 backend/.env 中设置。</p>
                </div>
              </div>
              <div className="setting-action">
                <Badge tone={capabilities?.ai_key_configured ? 'success' : 'neutral'}>
                  {capabilities?.ai_key_configured ? '已配置' : '未配置'}
                </Badge>
              </div>
            </div>

            <div className="setting-row">
              <div className="setting-info">
                <span className="setting-icon"><ShieldCheck size={17} /></span>
                <div>
                  <strong>本地 RapidOCR</strong>
                  <p>{capabilities?.ocr_message ?? '正在读取 OCR 状态…'}</p>
                </div>
              </div>
              <div className="setting-action">
                <Badge tone={capabilities?.ocr_available ? 'success' : 'warning'}>
                  {capabilities?.ocr_available ? '可用' : capabilities?.ocr_enabled ? '不可用' : '已禁用'}
                </Badge>
              </div>
            </div>

            <div className="setting-row">
              <div className="setting-info">
                <span className="setting-icon"><Info size={17} /></span>
                <div>
                  <strong>拆解与回退策略</strong>
                  <p>规则结果先生成；AI 超时、返回结构或证据引用不合法时显式回退。材料核验始终使用本地规则，不调用大模型。</p>
                </div>
              </div>
            </div>

            {capabilityError && <p className="inline-error" role="alert">{capabilityError}</p>}
            {aiTestResult && (
              <div className={`notice-bar ${aiTestResult.success ? '' : 'warning'}`} role="status">
                {aiTestResult.success ? <ShieldCheck size={15} /> : <AlertCircle size={15} />}
                <span>{aiTestResult.message}（模型：{aiTestResult.model || '未设置'}，耗时 {aiTestResult.elapsed_ms} 毫秒）</span>
              </div>
            )}
          </SectionCard>

          <SectionCard title="隐私说明" description="当前版本的数据处理方式">
            <div className="privacy-text">
              <p>
                上传的材料文件会发送到本机运行的后端服务，保存在
                <code>backend/data/uploads/materials</code>
                目录；事项、任务、材料与风险记录保存在
                <code>backend/data/taskradar.db</code>
                这一 SQLite 文件中。刷新或重启后数据仍然存在。
              </p>
              <p>
                业务记录和 OCR 均在本机处理。{capabilities?.ai_configured
                  ? '当前已配置模型服务：智能分析所需的文档文本会发送到该服务，请在上传前确认文档允许这样处理；服务地址与密钥不会展示在前端。'
                  : '当前未完整配置模型服务，智能分析只使用本地规则，不会把文档文本发送给第三方模型服务。'}
              </p>
              <p>
                当前版本没有云端同步，业务数据不会同步到云端，也没有多用户与权限管理：能访问本机文件的人都可以直接读取数据库与上传目录。
              </p>
              <p>
                当前版本不提供自动备份。需要留存数据时，请先停止后端服务，用 SQLite 备份工具导出
                <code>backend/data/taskradar.db</code>
                （不要直接复制 .db 文件，WAL 模式下可能丢数据），并复制
                <code>backend/data/uploads/materials</code> 目录。
              </p>
              <p>
                智能分析在配置模型后可调用大模型，失败时回退到本地规则；材料核验始终只依据文件文本与材料要求原文给出规则线索。
                核验不代表对材料真实性的证明；无法判断时会标记为「无法判断」，并可由你人工确认。
              </p>
            </div>
          </SectionCard>
        </div>

        <div className="stack">
          <SectionCard
            title="系统运行信息"
            description="实时读取后端健康检查接口"
            action={
              <Button variant="ghost" size="sm" onClick={() => void refresh()} disabled={loading}>
                <RefreshCw size={14} className={loading ? 'spin' : undefined} />
                重新检测
              </Button>
            }
          >
            <div className="status-list">
              <div className="status-row">
                <span>后端服务</span>
                <strong className={online ? 'text-success' : 'text-danger'}>
                  {loading ? '检测中…' : online ? '已连接' : '未连接'}
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
                <span>后端版本</span>
                <strong>{data?.version ?? '—'}</strong>
              </div>
              <div className="status-row">
                <span>最后检测</span>
                <strong>{checkedAt ?? '—'}</strong>
              </div>
            </div>
            {error && <p className="inline-error">{error}。请确认后端服务已启动。</p>}
            <a
              className="btn btn-secondary btn-sm external-link"
              href="http://127.0.0.1:8000/docs"
              target="_blank"
              rel="noreferrer"
            >
              打开接口文档
              <ExternalLink size={14} />
            </a>
          </SectionCard>

          <SectionCard title="数据管理" description="本地数据库与上传文件的存放位置">
            <div className="setting-row column">
              <div className="setting-info">
                <span className="setting-icon">
                  <Database size={17} />
                </span>
                <div>
                  <strong>数据库位置</strong>
                  <p>
                    后端 SQLite 文件：<code>backend/data/taskradar.db</code>
                  </p>
                </div>
              </div>
            </div>
            <div className="setting-row column">
              <div className="setting-info">
                <span className="setting-icon">
                  <FileText size={17} />
                </span>
                <div>
                  <strong>上传文件位置</strong>
                  <p>
                    材料文件保存在：<code>backend/data/uploads/materials</code>
                  </p>
                </div>
              </div>
            </div>
            <div className="setting-row">
              <div className="setting-info">
                <span className="setting-icon">
                  <Info size={17} />
                </span>
                <div>
                  <strong>导出数据</strong>
                  <p>
                    当前版本未提供应用内导出功能。数据以 SQLite 文件与上传目录形式保存在本机；
                    数据库请用 SQLite 备份工具导出（WAL 模式下不要直接复制 .db），
                    上传目录可直接复制留存。
                  </p>
                </div>
              </div>
              <div className="setting-action">
                <Badge tone="neutral">未实现</Badge>
                <Button variant="secondary" size="sm" disabled>
                  导出
                </Button>
              </div>
            </div>
            <div className="setting-row">
              <div className="setting-info">
                <span className="setting-icon">
                  <RefreshCw size={17} />
                </span>
                <div>
                  <strong>数据备份</strong>
                  <p>
                    当前版本没有自动备份。请在停止后端服务后，用 SQLite 备份工具导出
                    <code>backend/data/taskradar.db</code>
                    （不要直接复制 .db 文件，WAL 模式下可能丢数据），并复制上传目录；
                    页面刷新不会清空或重置任何业务数据。
                  </p>
                </div>
              </div>
            </div>
          </SectionCard>

          <SectionCard
            title="参赛演示数据"
            description="独立于正式数据，可在总览页切换查看"
            action={
              <Button
                variant="ghost"
                size="sm"
                onClick={() => void loadDemoStatus()}
                disabled={demoBusy}
              >
                <RefreshCw size={14} />
                刷新状态
              </Button>
            }
          >
            <div className="setting-row">
              <div className="setting-info">
                <span className="setting-icon">
                  <FlaskConical size={17} />
                </span>
                <div>
                  <strong>演示数据状态</strong>
                  <p>
                    {demoStatus === null
                      ? '正在读取演示数据状态…'
                      : demoStatus.seeded
                        ? `已初始化：${demoStatus.matters} 个事项、${demoStatus.tasks} 个任务、${demoStatus.materials} 项材料、${demoStatus.risks} 条风险。正式事项 ${demoStatus.real_matters} 个。`
                        : `尚未初始化。当前正式事项 ${demoStatus.real_matters} 个，正式数据不会参与演示。`}
                  </p>
                  {demoStatus?.seeded_at && (
                    <p className="muted-note">
                      初始化时间：{formatDateTime(demoStatus.seeded_at)}
                    </p>
                  )}
                </div>
              </div>
              <div className="setting-action">
                <Badge tone={demoStatus?.seeded ? 'demo' : 'neutral'}>
                  {demoStatus?.seeded ? '演示数据已就绪' : '未初始化'}
                </Badge>
              </div>
            </div>

            <div className="setting-row">
              <div className="setting-info">
                <span className="setting-icon">
                  <FlaskConical size={17} />
                </span>
                <div>
                  <strong>一键初始化</strong>
                  <p>
                    写入活动、竞赛、招聘三份演示通知及事项、任务、材料与多等级风险，
                    全部标记为演示数据；已初始化时不会重复写入。
                  </p>
                </div>
              </div>
              <div className="setting-action">
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => void handleSeed()}
                  disabled={demoBusy || demoStatus?.seeded === true}
                >
                  {demoBusy ? '处理中…' : '初始化演示数据'}
                </Button>
              </div>
            </div>

            <div className="setting-row">
              <div className="setting-info">
                <span className="setting-icon">
                  <RefreshCw size={17} />
                </span>
                <div>
                  <strong>刷新演示数据</strong>
                  <p>
                    清空并按今天重新计算演示数据的所有截止日期，避免演示前日期漂移；
                    不影响正式数据，也不需要先清理再初始化。
                  </p>
                </div>
              </div>
              <div className="setting-action">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setConfirmRefresh(true)}
                  disabled={demoBusy || demoStatus?.seeded !== true}
                >
                  刷新演示数据
                </Button>
              </div>
            </div>

            <div className="setting-row">
              <div className="setting-info">
                <span className="setting-icon">
                  <Trash2 size={17} />
                </span>
                <div>
                  <strong>一键清理</strong>
                  <p>
                    只删除标记为演示数据的事项及其任务、材料与风险，并清理演示材料文件；
                    正式数据与正式材料文件不会被删除。
                  </p>
                </div>
              </div>
              <div className="setting-action">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setConfirmClear(true)}
                  disabled={demoBusy || demoStatus?.seeded !== true}
                >
                  清理演示数据
                </Button>
              </div>
            </div>

            {demoError && (
              <p className="inline-error" role="alert">
                {demoError}
              </p>
            )}
          </SectionCard>

          <p className="settings-footnote">
            办事雷达 TaskRadar AI · AI + 本地 OCR（支持规则回退） · 业务记录保存在本机 SQLite
          </p>
        </div>
      </div>

      <Modal
        open={confirmRefresh}
        title="确认刷新演示数据？"
        description="会按今天重新计算所有截止日期，不影响正式数据。"
        onClose={() => {
          if (!demoBusy) setConfirmRefresh(false)
        }}
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => setConfirmRefresh(false)}
              disabled={demoBusy}
            >
              取消
            </Button>
            <Button variant="primary" onClick={() => void handleRefresh()} disabled={demoBusy}>
              {demoBusy ? '正在刷新…' : '确认刷新演示数据'}
            </Button>
          </>
        }
      >
        <p className="muted-note">
          会先删除当前的 {demoStatus?.matters ?? 0} 个演示事项及其任务、材料与风险，
          再按今天重新写入同一套演示数据。截止日期会重新计算，正式数据与正式材料文件不受影响。
        </p>
      </Modal>

      <Modal
        open={confirmClear}
        title="确认清理演示数据？"
        description="该操作只删除演示数据，不影响正式事项、任务、材料与风险。"
        onClose={() => {
          if (!demoBusy) setConfirmClear(false)
        }}
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => setConfirmClear(false)}
              disabled={demoBusy}
            >
              取消
            </Button>
            <Button variant="danger" onClick={() => void handleClear()} disabled={demoBusy}>
              {demoBusy ? '正在清理…' : '确认清理演示数据'}
            </Button>
          </>
        }
      >
        <p className="muted-note">
          将删除 {demoStatus?.matters ?? 0} 个演示事项、{demoStatus?.tasks ?? 0} 个任务、
          {demoStatus?.materials ?? 0} 项材料和 {demoStatus?.risks ?? 0} 条风险。
          正式数据不会被删除，清理后总览的正式统计保持不变。
        </p>
      </Modal>
    </div>
  )
}
