import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AlertCircle,
  Check,
  CheckCircle2,
  Clock3,
  FileText,
  ListChecks,
  Plus,
  RefreshCw,
  Route,
  Search,
  Sparkles,
  StickyNote,
} from 'lucide-react'
import {
  createMatter,
  fetchMatter,
  fetchMatters,
  MatterRequestError,
  updateMatter,
} from '../api/matters'
import { fetchTasks, generateTasksForMatter, taskErrorMessage, updateTask } from '../api/tasks'
import { refreshRisks } from '../api/risks'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { PageHeader } from '../components/ui/PageHeader'
import { Modal } from '../components/ui/Modal'
import { SectionCard } from '../components/ui/Card'
import { useToast } from '../components/ui/Toast'
import { deadlineSourceMeta, matterStatusMeta, priorityMeta } from '../lib/meta'
import { formatDateTime } from '../lib/format'
import type {
  Evidence,
  MatterRecord,
  MatterStatus,
  MatterUpdatePayload,
  TaskGenerationResult,
  TaskRecord,
} from '../types'
import type { RouteKey } from '../hooks/useHashRoute'

const statusOptions: { value: 'all' | MatterStatus; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'in_progress', label: '进行中' },
  { value: 'pending', label: '待开始' },
  { value: 'done', label: '已完成' },
]

const editableStatuses: MatterStatus[] = ['pending', 'in_progress', 'done']

function errorMessage(reason: unknown, fallback: string): string {
  return reason instanceof MatterRequestError ? reason.message : fallback
}

/**
 * 校验并规范化用户输入的截止日期。
 * 支持 2026-11-20 与 2026年11月20日 两种格式；空字符串表示清除。
 */
function parseDeadlineInput(value: string): { value: string | null; error: string } {
  const text = value.trim()
  if (!text) return { value: null, error: '' }
  const match =
    /^(\d{4})-(\d{2})-(\d{2})$/.exec(text) ??
    /^(\d{4})年(\d{1,2})月(\d{1,2})日$/.exec(text)
  if (!match) {
    return { value: null, error: '日期格式应为 2026-11-20 或 2026年11月20日。' }
  }
  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  const parsed = new Date(year, month - 1, day)
  if (
    parsed.getFullYear() !== year ||
    parsed.getMonth() !== month - 1 ||
    parsed.getDate() !== day
  ) {
    return { value: null, error: '日期不存在，请检查月份与天数是否正确。' }
  }
  return { value: text, error: '' }
}

function EvidenceLine({ evidence }: { evidence: Evidence }) {
  return (
    <p className="evidence-line">
      来源：{evidence.location} ·「{evidence.text}」
    </p>
  )
}

type MattersPageProps = {
  onNavigate: (key: RouteKey) => void
  focusMatterId?: number
}

export function MattersPage({ onNavigate, focusMatterId }: MattersPageProps) {
  const [matters, setMatters] = useState<MatterRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [keyword, setKeyword] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | MatterStatus>('all')
  const [typeFilter, setTypeFilter] = useState<string>('all')

  const [createOpen, setCreateOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState('')
  const [form, setForm] = useState({ name: '', matterType: '', deadline: '' })

  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<MatterRecord | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')
  const [draftName, setDraftName] = useState('')
  const [draftStatus, setDraftStatus] = useState<MatterStatus>('pending')
  const [draftDeadline, setDraftDeadline] = useState('')
  const [deadlineError, setDeadlineError] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')

  const [matterTasks, setMatterTasks] = useState<TaskRecord[]>([])
  const [tasksLoading, setTasksLoading] = useState(false)
  const [tasksError, setTasksError] = useState('')
  const [generating, setGenerating] = useState(false)
  const [generateMessage, setGenerateMessage] = useState('')
  const [suggestion, setSuggestion] = useState<TaskGenerationResult['suggestion']>(null)
  const [applying, setApplying] = useState(false)

  const { showToast } = useToast()

  const loadMatters = useCallback(async () => {
    setLoading(true)
    setLoadError('')
    try {
      const data = await fetchMatters()
      setMatters(data)
    } catch (reason) {
      setLoadError(errorMessage(reason, '读取事项列表失败，请确认后端服务是否正常。'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadMatters()
  }, [loadMatters])

  const typeOptions = useMemo(
    () =>
      Array.from(new Set(matters.map((matter) => matter.matter_type).filter(Boolean))).sort(),
    [matters],
  )

  const filteredMatters = useMemo(() => {
    const text = keyword.trim().toLowerCase()
    return matters.filter((matter) => {
      const matchKeyword = text === '' || matter.name.toLowerCase().includes(text)
      const matchStatus = statusFilter === 'all' || matter.status === statusFilter
      const matchType = typeFilter === 'all' || matter.matter_type === typeFilter
      return matchKeyword && matchStatus && matchType
    })
  }, [matters, keyword, statusFilter, typeFilter])

  const statusCount = (value: 'all' | MatterStatus) =>
    value === 'all' ? matters.length : matters.filter((matter) => matter.status === value).length

  const resetFilters = () => {
    setKeyword('')
    setStatusFilter('all')
    setTypeFilter('all')
  }

  const closeCreate = () => {
    if (creating) return
    setCreateOpen(false)
    setCreateError('')
  }

  const handleCreate = async () => {
    if (creating) return
    const name = form.name.trim()
    if (!name) {
      setCreateError('请填写事项名称。')
      return
    }

    setCreating(true)
    setCreateError('')
    try {
      const saved = await createMatter({
        name,
        matter_type: form.matterType.trim(),
        deadline: form.deadline.trim() || null,
        status: 'pending',
      })
      setCreateOpen(false)
      setForm({ name: '', matterType: '', deadline: '' })
      await loadMatters()
      showToast(`已创建事项 #${saved.id}，并写入 SQLite。`, 'success')
    } catch (reason) {
      const message = errorMessage(reason, '创建事项失败，请稍后重试。')
      setCreateError(message)
      showToast(message, 'warning')
    } finally {
      setCreating(false)
    }
  }

  const openDetail = async (matterId: number) => {
    setSelectedId(matterId)
    setDetail(null)
    setDetailError('')
    setSaveError('')
    setDeadlineError('')
    setMatterTasks([])
    setTasksError('')
    setGenerateMessage('')
    setSuggestion(null)
    setDetailLoading(true)
    setTasksLoading(true)
    try {
      const data = await fetchMatter(matterId)
      setDetail(data)
      setDraftName(data.name)
      setDraftStatus(data.status)
      setDraftDeadline(data.deadline ?? '')
      setDeadlineError('')
    } catch (reason) {
      setDetailError(errorMessage(reason, '读取事项详情失败，请稍后重试。'))
    } finally {
      setDetailLoading(false)
    }

    try {
      const tasks = await fetchTasks({ matterId })
      setMatterTasks(tasks)
    } catch (reason) {
      setTasksError(taskErrorMessage(reason, '读取关联任务失败，请稍后重试。'))
    } finally {
      setTasksLoading(false)
    }
  }

  useEffect(() => {
    if (focusMatterId) {
      void openDetail(focusMatterId)
    }
    // 仅在跳转参数变化时打开对应事项详情。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusMatterId])

  const handleGenerateTasks = async () => {
    if (!detail || generating) return
    setGenerating(true)
    setTasksError('')
    setGenerateMessage('')
    try {
      const result = await generateTasksForMatter(detail.id)
      if (result.created > 0) {
        setMatterTasks((current) => [...result.tasks, ...current])
        setSuggestion(result.suggestion)
        showToast(result.message, 'success')
      } else {
        showToast(result.message, 'warning')
      }
      setGenerateMessage(result.message)
    } catch (reason) {
      const message = taskErrorMessage(reason, '生成任务失败，请稍后重试。')
      setTasksError(message)
      showToast(message, 'warning')
    } finally {
      setGenerating(false)
    }
  }

  const handleApplySuggestion = async () => {
    if (!detail || !suggestion || !suggestion.deadline || applying) return
    const matterId = detail.id
    const currentSuggestion = suggestion
    setApplying(true)
    setTasksError('')
    try {
      const results = await Promise.allSettled(
        currentSuggestion.task_ids.map((taskId) =>
          updateTask(taskId, {
            deadline: currentSuggestion.deadline,
            // 用户点击「应用建议」即视为明确确认，按人工设置参与正式截止提醒。
            deadline_source: 'manual',
          }),
        ),
      )
      const updated = results.flatMap((result) =>
        result.status === 'fulfilled' ? [result.value] : [],
      )
      const failedTaskIds = currentSuggestion.task_ids.filter(
        (_taskId, index) => results[index].status === 'rejected',
      )
      const firstFailure = results.find(
        (result): result is PromiseRejectedResult => result.status === 'rejected',
      )

      // 先使用成功请求的真实响应更新，避免后续刷新失败时仍展示旧数据。
      if (updated.length > 0) {
        setMatterTasks((current) =>
          current.map((task) => updated.find((item) => item.id === task.id) ?? task),
        )
      }
      setSuggestion(
        failedTaskIds.length > 0
          ? { ...currentSuggestion, task_ids: failedTaskIds }
          : null,
      )

      let refreshError = ''
      if (updated.length > 0) {
        try {
          const refreshed = await fetchTasks({ matterId })
          setMatterTasks(refreshed)
        } catch (reason) {
          refreshError = taskErrorMessage(
            reason,
            '成功项目已保存，但重新读取任务失败，请手动刷新。',
          )
        }
      }

      const summary = `成功 ${updated.length} 个，失败 ${failedTaskIds.length} 个。`
      setGenerateMessage(summary)
      if (failedTaskIds.length > 0 || refreshError) {
        const failureDetail = firstFailure
          ? taskErrorMessage(firstFailure.reason, '部分任务更新失败。')
          : ''
        const retryHint = failedTaskIds.length > 0
          ? `失败任务 #${failedTaskIds.join('、#')} 已保留，可再次点击「应用建议」重试。`
          : ''
        const message = [summary, failureDetail, retryHint, refreshError]
          .filter(Boolean)
          .join(' ')
        setTasksError(message)
        showToast(message, 'warning')
      } else {
        showToast(`${summary}已为任务确认截止时间。`, 'success')
      }
    } finally {
      setApplying(false)
    }
  }

  const closeDetail = () => {
    if (saving) return
    setSelectedId(null)
    setDetail(null)
    setDetailError('')
    setSaveError('')
  }

  const handleUpdate = async () => {
    if (!detail || saving) return
    const name = draftName.trim()
    if (!name) {
      setSaveError('事项名称不能为空。')
      return
    }

    const deadline = parseDeadlineInput(draftDeadline)
    if (deadline.error) {
      setDeadlineError(deadline.error)
      setSaveError('')
      return
    }
    setDeadlineError('')

    const changes: MatterUpdatePayload = {}
    if (name !== detail.name) changes.name = name
    if (draftStatus !== detail.status) changes.status = draftStatus
    if ((deadline.value ?? '') !== (detail.deadline ?? '')) {
      changes.deadline = deadline.value
      // 用户手动确认的日期按 manual 记录；清空时回到 none。
      changes.deadline_source = deadline.value ? 'manual' : 'none'
    }

    if (Object.keys(changes).length === 0) {
      showToast('没有需要保存的修改。', 'warning')
      return
    }

    setSaving(true)
    setSaveError('')
    try {
      const updated = await updateMatter(detail.id, changes)
      await loadMatters()
      // 重新读取事项与关联任务，确保日期、任务和风险信息同步刷新。
      await openDetail(updated.id)
      try {
        await refreshRisks()
        showToast(`事项 #${updated.id} 已更新，关联任务与风险已刷新。`, 'success')
      } catch {
        showToast(
          `事项 #${updated.id} 已更新；风险分析刷新失败，可稍后在风险中心重新分析。`,
          'warning',
        )
      }
    } catch (reason) {
      const message = errorMessage(reason, '更新事项失败，请稍后重试。')
      setSaveError(message)
      showToast(message, 'warning')
    } finally {
      setSaving(false)
    }
  }

  const hasChanges =
    detail !== null &&
    (draftName.trim() !== detail.name ||
      draftStatus !== detail.status ||
      draftDeadline.trim() !== (detail.deadline ?? ''))

  return (
    <div className="page-stack">
      <PageHeader
        title="我的事项"
        description="以下事项来自本机 SQLite，由智能分析结果保存而来，刷新或重启后仍然存在。"
        badge={<Badge tone="success">本机数据</Badge>}
        actions={
          <>
            <Button variant="secondary" onClick={() => void loadMatters()} disabled={loading}>
              <RefreshCw size={16} />
              刷新
            </Button>
            <Button variant="primary" onClick={() => setCreateOpen(true)}>
              <Plus size={16} />
              新建事项
            </Button>
          </>
        }
      />

      <SectionCard
        title="事项列表"
        description={`共 ${matters.length} 个事项（数据来源：SQLite），当前显示 ${filteredMatters.length} 个`}
      >
        <div className="toolbar">
          <div className="search-box">
            <Search size={16} />
            <input
              type="search"
              placeholder="搜索事项名称"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              aria-label="搜索事项名称"
            />
          </div>

          <div className="filter-group" role="group" aria-label="按状态筛选">
            {statusOptions.map((option) => (
              <button
                key={option.value}
                type="button"
                className={`filter-chip ${statusFilter === option.value ? 'active' : ''}`.trim()}
                onClick={() => setStatusFilter(option.value)}
              >
                {option.label}
                <span>{statusCount(option.value)}</span>
              </button>
            ))}
          </div>

          <select
            className="select"
            value={typeFilter}
            onChange={(event) => setTypeFilter(event.target.value)}
            aria-label="按事项类型筛选"
          >
            <option value="all">全部类型</option>
            {typeOptions.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </div>

        {loadError && (
          <div className="inline-error" role="alert">
            <AlertCircle size={15} />
            <span>{loadError}</span>
          </div>
        )}

        {loading ? (
          <p className="muted-note">正在读取事项列表…</p>
        ) : filteredMatters.length === 0 ? (
          <div className="empty-state">
            <Search size={22} />
            <strong>{matters.length === 0 ? '还没有保存的事项' : '没有找到匹配的事项'}</strong>
            <p>
              {matters.length === 0
                ? '前往「智能分析」上传文档，分析完成后点击「保存为事项」。'
                : '换一个关键词，或清空筛选条件后再试。'}
            </p>
            {matters.length === 0 ? (
              <Button variant="primary" size="sm" onClick={() => onNavigate('analyze')}>
                前往智能分析
              </Button>
            ) : (
              <Button variant="secondary" size="sm" onClick={resetFilters}>
                清空筛选
              </Button>
            )}
          </div>
        ) : (
          <div className="matter-table">
            <div className="matter-head" aria-hidden="true">
              <span>事项名称</span>
              <span>类型</span>
              <span>截止日期</span>
              <span>状态</span>
              <span>操作</span>
            </div>
            {filteredMatters.map((matter) => {
              const status = matterStatusMeta[matter.status]
              return (
                <div className="matter-row" key={matter.id}>
                  <div className="matter-name-cell">
                    <span className="row-icon">
                      <FileText size={16} />
                    </span>
                    <div>
                      <div className="name-with-badge">
                        <strong>{matter.name}</strong>
                        {matter.is_demo && <Badge tone="demo">演示数据</Badge>}
                      </div>
                      <small>
                        #{matter.id} · {matter.source_filename || '手动创建'} · 更新于{' '}
                        {formatDateTime(matter.updated_at)}
                      </small>
                    </div>
                  </div>
                  <span className="type-chip">{matter.matter_type || '未分类'}</span>
                  <span className="deadline-cell">
                    <Clock3 size={14} />
                    {matter.deadline || '待核实'}
                  </span>
                  <span>
                    <Badge tone={status.tone}>{status.label}</Badge>
                  </span>
                  <span className="row-action">
                    <Button variant="ghost" size="sm" onClick={() => void openDetail(matter.id)}>
                      查看
                    </Button>
                  </span>
                </div>
              )
            })}
          </div>
        )}

        <p className="muted-note">
          事项均真实保存在本机数据库；标记「演示数据」的记录来自参赛演示数据，可在设置页一键清理。
        </p>
      </SectionCard>

      <Modal
        open={createOpen}
        title="新建事项"
        description="保存后写入后端 SQLite，刷新或重启后仍然存在。"
        onClose={closeCreate}
        footer={
          <>
            <Button variant="secondary" onClick={closeCreate} disabled={creating}>
              取消
            </Button>
            <Button variant="primary" onClick={() => void handleCreate()} disabled={creating}>
              {creating ? '正在保存…' : '保存事项'}
            </Button>
          </>
        }
      >
        <div className="form-grid">
          <label className="field">
            <span>
              事项名称 <em>*</em>
            </span>
            <input
              className="input"
              type="text"
              placeholder="例如：第十四届百花知遇话剧大赛报名"
              value={form.name}
              onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
            />
          </label>
          <label className="field">
            <span>事项类型</span>
            <input
              className="input"
              type="text"
              list="matter-type-options"
              placeholder="例如：活动赛事"
              value={form.matterType}
              onChange={(event) =>
                setForm((current) => ({ ...current, matterType: event.target.value }))
              }
            />
            <datalist id="matter-type-options">
              {typeOptions.map((type) => (
                <option key={type} value={type} />
              ))}
            </datalist>
          </label>
          <label className="field">
            <span>截止日期</span>
            <input
              className="input"
              type="text"
              placeholder="例如：2026年11月20日"
              value={form.deadline}
              onChange={(event) =>
                setForm((current) => ({ ...current, deadline: event.target.value }))
              }
            />
          </label>
        </div>
        {createError && (
          <div className="inline-error" role="alert">
            <AlertCircle size={15} />
            <span>{createError}</span>
          </div>
        )}
        <p className="muted-note">手动新建的事项没有原文证据，详情页会明确标注。</p>
      </Modal>

      <Modal
        open={selectedId !== null}
        title={detail?.name ?? '事项详情'}
        description="以下内容读取自后端数据库，原文证据与保存时一致。"
        onClose={closeDetail}
        footer={
          <>
            <Button variant="secondary" onClick={closeDetail} disabled={saving}>
              关闭
            </Button>
            <Button
              variant="primary"
              onClick={() => void handleUpdate()}
              disabled={saving || !detail || !hasChanges}
            >
              {saving ? '正在保存…' : '保存修改'}
            </Button>
          </>
        }
      >
        {detailLoading ? (
          <p className="muted-note">正在读取事项详情…</p>
        ) : detailError ? (
          <div className="inline-error" role="alert">
            <AlertCircle size={15} />
            <span>{detailError}</span>
          </div>
        ) : detail ? (
          <div className="stack">
            {detail.is_demo && (
              <div className="notice-bar warning">
                <Badge tone="demo">演示数据</Badge>
                <span>
                  该事项由参赛演示数据初始化生成，仅用于展示完整流程，不是真实用户数据。
                </span>
              </div>
            )}
            <div className="form-grid">
              <label className="field">
                <span>事项名称</span>
                <input
                  className="input"
                  type="text"
                  value={draftName}
                  onChange={(event) => setDraftName(event.target.value)}
                />
              </label>
              <label className="field">
                <span>事项状态</span>
                <select
                  className="select"
                  value={draftStatus}
                  onChange={(event) => setDraftStatus(event.target.value as MatterStatus)}
                >
                  {editableStatuses.map((value) => (
                    <option key={value} value={value}>
                      {matterStatusMeta[value].label}
                    </option>
                  ))}
                </select>
              </label>
              <div className="field">
                <span>截止日期</span>
                <div className="toolbar" style={{ marginBottom: 0 }}>
                  <input
                    className="input"
                    type="text"
                    placeholder="例如：2026-11-20 或 2026年11月20日"
                    value={draftDeadline}
                    style={{ flex: 1 }}
                    aria-label="事项截止日期"
                    aria-invalid={Boolean(deadlineError)}
                    onChange={(event) => {
                      setDraftDeadline(event.target.value)
                      setDeadlineError('')
                    }}
                  />
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setDraftDeadline('')
                      setDeadlineError('')
                    }}
                  >
                    清除
                  </Button>
                </div>
                <small className="muted-note">
                  当前来源：{deadlineSourceMeta[detail.deadline_source] ?? detail.deadline_source}
                  {detail.deadline_source === 'suggested' &&
                    '；未确认的系统建议不会自动转为正式截止日期'}
                </small>
                {deadlineError && (
                  <div className="inline-error" role="alert">
                    <AlertCircle size={15} />
                    <span>{deadlineError}</span>
                  </div>
                )}
              </div>
            </div>

            {saveError && (
              <div className="inline-error" role="alert">
                <AlertCircle size={15} />
                <span>{saveError}</span>
              </div>
            )}

            <dl className="detail-list">
              <div>
                <dt>事项编号</dt>
                <dd>#{detail.id}</dd>
              </div>
              <div>
                <dt>事项类型</dt>
                <dd>{detail.matter_type || '未识别'}</dd>
              </div>
              <div>
                <dt>报名开始日期</dt>
                <dd>{detail.registration_start || '待核实'}</dd>
              </div>
              <div>
                <dt>截止日期</dt>
                <dd>{detail.deadline || '待核实'}</dd>
              </div>
              <div>
                <dt>来源文件</dt>
                <dd>{detail.source_filename || '手动创建'}</dd>
              </div>
              <div>
                <dt>创建时间</dt>
                <dd>{formatDateTime(detail.created_at)}</dd>
              </div>
              <div>
                <dt>最近更新</dt>
                <dd>{formatDateTime(detail.updated_at)}</dd>
              </div>
            </dl>

            <div>
              <strong>申请资格</strong>
              <p className="muted-note">{detail.qualification || '原文未写明，待核实。'}</p>
            </div>

            <div>
              <strong>
                <ListChecks size={14} /> 所需材料（{detail.materials.length}）
              </strong>
              {detail.materials.length === 0 ? (
                <p className="empty-hint">该事项未保存材料清单。</p>
              ) : (
                <ul className="result-items">
                  {detail.materials.map((item, index) => (
                    <li className="result-item" key={`${item.name}-${index}`}>
                      <span className="result-icon">
                        <ListChecks size={15} />
                      </span>
                      <div>
                        <strong>{item.name}</strong>
                        <EvidenceLine evidence={item.evidence} />
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div>
              <strong>办理流程（{detail.process.length} 步）</strong>
              {detail.process.length === 0 ? (
                <p className="empty-hint">该事项未保存办理流程。</p>
              ) : (
                <ol className="result-items">
                  {detail.process.map((step) => (
                    <li className="result-item step" key={`${step.index}-${step.text}`}>
                      <span className="step-index">{String(step.index).padStart(2, '0')}</span>
                      <div>
                        <strong>{step.text}</strong>
                        <EvidenceLine evidence={step.evidence} />
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </div>

            <div>
              <div className="section-inline-head">
                <strong>
                  <ListChecks size={14} /> 关联任务（{matterTasks.length}）
                </strong>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => void handleGenerateTasks()}
                  disabled={generating || tasksLoading}
                >
                  <Sparkles size={14} />
                  {generating ? '正在生成…' : '生成任务'}
                </Button>
              </div>
              {generateMessage && <p className="muted-note">{generateMessage}</p>}
              {suggestion && (
                <div className="notice-bar">
                  <AlertCircle size={16} />
                  <span>
                    {suggestion.note} 建议截止时间：{suggestion.deadline}
                  </span>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => void handleApplySuggestion()}
                    disabled={applying}
                  >
                    {applying ? '应用中…' : '应用建议'}
                  </Button>
                </div>
              )}
              {tasksError && (
                <div className="inline-error" role="alert">
                  <AlertCircle size={15} />
                  <span>{tasksError}</span>
                </div>
              )}
              {tasksLoading ? (
                <p className="muted-note">正在读取关联任务…</p>
              ) : matterTasks.length === 0 ? (
                <p className="empty-hint">
                  尚未生成任务。点击「生成任务」按办理流程创建，截止时间留空时会给出系统建议。
                </p>
              ) : (
                <ul className="linked-task-list">
                  {matterTasks.map((task) => {
                    const priorityInfo = priorityMeta[task.priority]
                    return (
                      <li className="linked-task" key={task.id}>
                        <span
                          className={`task-check ${task.status === 'done' ? 'checked' : ''}`.trim()}
                          aria-hidden="true"
                        >
                          {task.status === 'done' && <Check size={12} />}
                        </span>
                        <div className="task-main">
                          <strong>{task.title}</strong>
                          <small>
                            #{task.id} · {task.origin === 'generated' ? '流程生成' : '手动添加'}
                          </small>
                        </div>
                        <Badge tone={priorityInfo.tone}>{priorityInfo.label}</Badge>
                        <span className="task-due">
                          <Clock3 size={13} />
                          {task.deadline || '未设置截止时间'}
                          {task.deadline_source !== 'none' && (
                            <em className={`deadline-tag ${task.deadline_source}`}>
                              {task.deadline_source === 'document'
                                ? '原文明确'
                                : task.deadline_source === 'suggested'
                                  ? '系统建议'
                                  : '手动设置'}
                            </em>
                          )}
                        </span>
                        <Badge
                          tone={
                            task.status === 'done'
                              ? 'success'
                              : task.status === 'in_progress'
                                ? 'info'
                                : 'neutral'
                          }
                        >
                          {task.status === 'done'
                            ? '已完成'
                            : task.status === 'in_progress'
                              ? '进行中'
                              : '待完成'}
                        </Badge>
                      </li>
                    )
                  })}
                </ul>
              )}
              <p className="muted-note">
                任务数据保存在 SQLite，可在
                <Button variant="ghost" size="sm" onClick={() => onNavigate('tasks')}>
                  任务中心
                </Button>
                修改、完成或删除。
              </p>
            </div>

            <div>
              <strong>
                <StickyNote size={14} /> 注意事项（{detail.notes.length}）
              </strong>
              {detail.notes.length === 0 ? (
                <p className="empty-hint">该事项未保存注意事项。</p>
              ) : (
                <ul className="result-items">
                  {detail.notes.map((note, index) => (
                    <li className="result-item" key={`${note.text}-${index}`}>
                      <span className="result-icon">
                        <Route size={15} />
                      </span>
                      <div>
                        <strong>{note.text}</strong>
                        <EvidenceLine evidence={note.evidence} />
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div>
              <strong>字段与原文证据</strong>
              {detail.fields.length === 0 ? (
                <p className="empty-hint">该事项没有保存字段级证据。</p>
              ) : (
                <div className="stack">
                  {detail.fields.map((field) => (
                    <div key={field.key}>
                      <p className="muted-note">
                        {field.label}：{field.value || '待核实'}
                      </p>
                      {field.evidence.length === 0 ? (
                        <p className="evidence-line">来源：原文未提供可定位证据</p>
                      ) : (
                        field.evidence.map((item, index) => (
                          <EvidenceLine evidence={item} key={`${field.key}-${index}`} />
                        ))
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {hasChanges && (
              <div className="notice-bar">
                <CheckCircle2 size={16} />
                <span>存在未保存的修改，点击右下角「保存修改」写入数据库。</span>
              </div>
            )}
          </div>
        ) : null}
      </Modal>
    </div>
  )
}
