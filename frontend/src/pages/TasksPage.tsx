import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertCircle,
  Check,
  Clock3,
  ListChecks,
  Pencil,
  Plus,
  RefreshCw,
  Trash2,
} from 'lucide-react'
import {
  createTask,
  deleteTask,
  fetchTasks,
  taskErrorMessage,
  updateTask,
} from '../api/tasks'
import { fetchMatters } from '../api/matters'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card, SectionCard } from '../components/ui/Card'
import { Modal } from '../components/ui/Modal'
import { PageHeader } from '../components/ui/PageHeader'
import { useToast } from '../components/ui/Toast'
import { priorityMeta } from '../lib/meta'
import type { MatterRecord, TaskPriority, TaskRecord, TaskStatus } from '../types'

const taskStatusLabels: Record<TaskStatus, string> = {
  pending: '待完成',
  in_progress: '进行中',
  done: '已完成',
}

const tabs: { key: TaskStatus; label: string }[] = [
  { key: 'pending', label: '待完成' },
  { key: 'in_progress', label: '进行中' },
  { key: 'done', label: '已完成' },
]

const priorityFilters: { value: 'all' | TaskPriority; label: string }[] = [
  { value: 'all', label: '全部优先级' },
  { value: 'high', label: '高' },
  { value: 'medium', label: '中' },
  { value: 'low', label: '低' },
]

const deadlineSourceLabels: Record<string, string> = {
  document: '原文明确',
  suggested: '系统建议',
  manual: '手动设置',
}

type EditForm = {
  title: string
  description: string
  deadline: string
  priority: TaskPriority
}

type CreateForm = EditForm & { matterId: string }

const emptyEditForm: EditForm = { title: '', description: '', deadline: '', priority: 'medium' }
const emptyCreateForm: CreateForm = { ...emptyEditForm, matterId: '' }

type TasksPageProps = {
  focusMatterId?: number
  focusTaskId?: number
}

export function TasksPage({ focusMatterId, focusTaskId }: TasksPageProps) {
  const [tasks, setTasks] = useState<TaskRecord[]>([])
  const [matters, setMatters] = useState<MatterRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [tab, setTab] = useState<TaskStatus>('pending')
  const [priority, setPriority] = useState<'all' | TaskPriority>('all')
  const [matterFilter, setMatterFilter] = useState(
    focusMatterId ? String(focusMatterId) : 'all',
  )
  const focusApplied = useRef<number | null>(null)
  const { showToast } = useToast()

  const [editing, setEditing] = useState<TaskRecord | null>(null)
  const [editForm, setEditForm] = useState<EditForm>(emptyEditForm)
  const [editError, setEditError] = useState('')
  const [saving, setSaving] = useState(false)

  const [deleting, setDeleting] = useState<TaskRecord | null>(null)
  const [deleteError, setDeleteError] = useState('')
  const [removing, setRemoving] = useState(false)

  const [createOpen, setCreateOpen] = useState(false)
  const [createForm, setCreateForm] = useState<CreateForm>(emptyCreateForm)
  const [createError, setCreateError] = useState('')
  const [creating, setCreating] = useState(false)

  const loadData = useCallback(async () => {
    setLoading(true)
    setLoadError('')
    try {
      const [taskList, matterList] = await Promise.all([fetchTasks(), fetchMatters()])
      setTasks(taskList)
      setMatters(matterList)
    } catch (reason) {
      setLoadError(taskErrorMessage(reason, '读取任务列表失败，请确认后端服务是否正常。'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadData()
  }, [loadData])

  useEffect(() => {
    // 记录已应用的任务编号而不是布尔值：同一页面内切换到另一个任务时也要生效。
    if (!focusTaskId || focusApplied.current === focusTaskId || tasks.length === 0) {
      return
    }
    const target = tasks.find((task) => task.id === focusTaskId)
    if (!target) return
    focusApplied.current = focusTaskId
    setTab(target.status)
    setMatterFilter(String(target.matter_id))
  }, [focusTaskId, tasks])

  const matterNames = useMemo(() => {
    const map = new Map<number, string>()
    matters.forEach((matter) => map.set(matter.id, matter.name))
    return map
  }, [matters])

  const matterTasks = useMemo(
    () =>
      matterFilter === 'all'
        ? tasks
        : tasks.filter((task) => String(task.matter_id) === matterFilter),
    [tasks, matterFilter],
  )

  const counts = useMemo(
    () => ({
      pending: matterTasks.filter((task) => task.status === 'pending').length,
      in_progress: matterTasks.filter((task) => task.status === 'in_progress').length,
      done: matterTasks.filter((task) => task.status === 'done').length,
    }),
    [matterTasks],
  )

  const visibleTasks = useMemo(() => {
    const list = matterTasks.filter((task) => task.status === tab)
    return priority === 'all' ? list : list.filter((task) => task.priority === priority)
  }, [matterTasks, tab, priority])

  const completedRate =
    matterTasks.length === 0 ? 0 : Math.round((counts.done / matterTasks.length) * 100)

  const replaceTask = (updated: TaskRecord) => {
    setTasks((current) => current.map((item) => (item.id === updated.id ? updated : item)))
  }

  const handleToggle = async (task: TaskRecord) => {
    const nextStatus: TaskStatus = task.status === 'done' ? 'pending' : 'done'
    try {
      const updated = await updateTask(task.id, { status: nextStatus })
      replaceTask(updated)
      showToast(
        nextStatus === 'done'
          ? `任务「${updated.title}」已完成。`
          : `任务「${updated.title}」已重新打开。`,
        'success',
      )
    } catch (reason) {
      showToast(taskErrorMessage(reason, '更新任务状态失败，请稍后重试。'), 'warning')
    }
  }

  const openEdit = (task: TaskRecord) => {
    setEditing(task)
    setEditForm({
      title: task.title,
      description: task.description,
      deadline: task.deadline ?? '',
      priority: task.priority,
    })
    setEditError('')
  }

  const closeEdit = () => {
    if (saving) return
    setEditing(null)
    setEditError('')
  }

  const handleSaveEdit = async () => {
    if (!editing || saving) return
    const title = editForm.title.trim()
    if (!title) {
      setEditError('任务名称不能为空。')
      return
    }
    const deadline = editForm.deadline.trim()
    const changes: {
      title?: string
      description?: string
      deadline?: string | null
      priority?: TaskPriority
    } = {}
    if (title !== editing.title) changes.title = title
    if (editForm.description.trim() !== editing.description) {
      changes.description = editForm.description.trim()
    }
    if (deadline !== (editing.deadline ?? '')) changes.deadline = deadline || null
    if (editForm.priority !== editing.priority) changes.priority = editForm.priority

    if (Object.keys(changes).length === 0) {
      showToast('没有需要保存的修改。', 'warning')
      return
    }

    setSaving(true)
    setEditError('')
    try {
      const updated = await updateTask(editing.id, changes)
      replaceTask(updated)
      setEditing(null)
      showToast(`任务 #${updated.id} 已更新。`, 'success')
    } catch (reason) {
      const message = taskErrorMessage(reason, '更新任务失败，请稍后重试。')
      setEditError(message)
      showToast(message, 'warning')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!deleting || removing) return
    setRemoving(true)
    setDeleteError('')
    try {
      await deleteTask(deleting.id)
      setTasks((current) => current.filter((item) => item.id !== deleting.id))
      showToast(`任务 #${deleting.id} 已删除。`, 'success')
      setDeleting(null)
    } catch (reason) {
      const message = taskErrorMessage(reason, '删除任务失败，请稍后重试。')
      setDeleteError(message)
      showToast(message, 'warning')
    } finally {
      setRemoving(false)
    }
  }

  const openCreate = () => {
    setCreateForm({ ...emptyCreateForm, matterId: matters[0] ? String(matters[0].id) : '' })
    setCreateError('')
    setCreateOpen(true)
  }

  const handleCreate = async () => {
    if (creating) return
    const title = createForm.title.trim()
    if (!createForm.matterId) {
      setCreateError('请选择任务所属事项。')
      return
    }
    if (!title) {
      setCreateError('任务名称不能为空。')
      return
    }
    setCreating(true)
    setCreateError('')
    try {
      const saved = await createTask({
        matter_id: Number(createForm.matterId),
        title,
        description: createForm.description.trim(),
        deadline: createForm.deadline.trim() || null,
        priority: createForm.priority,
        status: 'pending',
      })
      setTasks((current) => [saved, ...current])
      setTab('pending')
      setCreateOpen(false)
      showToast(`已新增任务 #${saved.id}，并写入 SQLite。`, 'success')
    } catch (reason) {
      const message = taskErrorMessage(reason, '新增任务失败，请稍后重试。')
      setCreateError(message)
      showToast(message, 'warning')
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="任务中心"
        description="任务由事项办理流程生成，全部保存在本机 SQLite，可修改、完成、重新打开或删除。"
        badge={<Badge tone="success">本机数据</Badge>}
        actions={
          <>
            <Button variant="secondary" onClick={() => void loadData()} disabled={loading}>
              <RefreshCw size={16} />
              刷新
            </Button>
            <Button variant="primary" onClick={openCreate} disabled={matters.length === 0}>
              <Plus size={16} />
              新建任务
            </Button>
          </>
        }
      />

      <Card className="task-summary">
        <div className="task-summary-text">
          <span className="summary-icon">
            <ListChecks size={18} />
          </span>
          <div>
            <strong>任务完成进度</strong>
            <p>
              共 {matterTasks.length} 项任务，已完成 {counts.done} 项，待完成 {counts.pending} 项，进行中{' '}
              {counts.in_progress} 项。
            </p>
          </div>
        </div>
        <div className="task-summary-progress">
          <div className="verify-progress-head">
            <span>完成率</span>
            <strong>{completedRate}%</strong>
          </div>
          <div className="progress">
            <span style={{ width: `${completedRate}%` }} />
          </div>
        </div>
      </Card>

      <SectionCard
        title="任务列表"
        description="勾选任务可标记完成，再次点击可重新打开；数据来源：SQLite"
      >
        <div className="toolbar toolbar-wrap">
          <div className="tabs" role="tablist" aria-label="任务分组">
            {tabs.map((item) => (
              <button
                key={item.key}
                type="button"
                role="tab"
                aria-selected={tab === item.key}
                className={`tab ${tab === item.key ? 'active' : ''}`.trim()}
                onClick={() => setTab(item.key)}
              >
                {item.label}
                <span>{counts[item.key]}</span>
              </button>
            ))}
          </div>

          <div className="filter-group" role="group" aria-label="按优先级筛选">
            {priorityFilters.map((item) => (
              <button
                key={item.value}
                type="button"
                className={`filter-chip ${priority === item.value ? 'active' : ''}`.trim()}
                onClick={() => setPriority(item.value)}
              >
                {item.label}
              </button>
            ))}
          </div>

          <label className="field task-matter-filter">
            <span>所属事项</span>
            <select
              className="select"
              value={matterFilter}
              onChange={(event) => setMatterFilter(event.target.value)}
            >
              <option value="all">全部事项</option>
              {matters.map((matter) => (
                <option key={matter.id} value={matter.id}>
                  #{matter.id} {matter.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        {loadError && (
          <div className="inline-error" role="alert">
            <AlertCircle size={15} />
            <span>{loadError}</span>
          </div>
        )}

        {loading ? (
          <p className="muted-note">正在读取任务列表…</p>
        ) : tasks.length === 0 ? (
          <div className="empty-state">
            <ListChecks size={22} />
            <strong>还没有任务</strong>
            <p>前往「我的事项」打开事项详情，点击「生成任务」，或在此手动新增任务。</p>
          </div>
        ) : visibleTasks.length === 0 ? (
          <div className="empty-state">
            <ListChecks size={22} />
            <strong>这个分组暂时没有任务</strong>
            <p>切换分组或调整优先级筛选后再看看。</p>
          </div>
        ) : (
          <ul className="task-list">
            {visibleTasks.map((task) => {
              const priorityInfo = priorityMeta[task.priority]
              return (
                <li
                  className={`task-row ${task.status === 'done' ? 'done' : ''} ${
                    focusTaskId === task.id ? 'focused' : ''
                  }`.trim()}
                  key={task.id}
                >
                  <button
                    type="button"
                    className={`task-check ${task.status === 'done' ? 'checked' : ''}`.trim()}
                    aria-label={
                      task.status === 'done'
                        ? `将「${task.title}」重新打开`
                        : `完成「${task.title}」`
                    }
                    onClick={() => void handleToggle(task)}
                  >
                    {task.status === 'done' && <Check size={13} />}
                  </button>
                  <div className="task-main">
                    <div className="name-with-badge">
                      <strong>{task.title}</strong>
                      {task.is_demo && <Badge tone="demo">演示数据</Badge>}
                    </div>
                    <small>
                      {matterNames.get(task.matter_id) ?? `事项 #${task.matter_id}`}
                      {task.origin === 'generated' ? ' · 流程生成' : ' · 手动添加'}
                    </small>
                  </div>
                  <Badge tone={priorityInfo.tone}>{priorityInfo.label}</Badge>
                  {task.deadline ? (
                    <span className="task-due">
                      <Clock3 size={14} />
                      {task.deadline}
                      {deadlineSourceLabels[task.deadline_source] && (
                        <em className={`deadline-tag ${task.deadline_source}`}>
                          {deadlineSourceLabels[task.deadline_source]}
                        </em>
                      )}
                    </span>
                  ) : (
                    <span className="task-due">
                      <Clock3 size={14} />
                      未设置截止时间
                    </span>
                  )}
                  <Badge tone={task.status === 'done' ? 'success' : task.status === 'in_progress' ? 'info' : 'neutral'}>
                    {taskStatusLabels[task.status]}
                  </Badge>
                  <span className="task-actions">
                    <button
                      type="button"
                      className="icon-btn"
                      aria-label={`编辑「${task.title}」`}
                      onClick={() => openEdit(task)}
                    >
                      <Pencil size={15} />
                    </button>
                    <button
                      type="button"
                      className="icon-btn"
                      aria-label={`删除「${task.title}」`}
                      onClick={() => {
                        setDeleting(task)
                        setDeleteError('')
                      }}
                    >
                      <Trash2 size={15} />
                    </button>
                  </span>
                </li>
              )
            })}
          </ul>
        )}
      </SectionCard>

      <Modal
        open={editing !== null}
        title={`编辑任务${editing ? ` #${editing.id}` : ''}`}
        description="修改会直接写入 SQLite 数据库。"
        onClose={closeEdit}
        footer={
          <>
            <Button variant="secondary" onClick={closeEdit} disabled={saving}>
              取消
            </Button>
            <Button variant="primary" onClick={() => void handleSaveEdit()} disabled={saving}>
              {saving ? '保存中…' : '保存修改'}
            </Button>
          </>
        }
      >
        <div className="form-grid">
          <label className="field">
            <span>任务名称 <em>*</em></span>
            <input
              className="input"
              value={editForm.title}
              onChange={(event) => setEditForm((form) => ({ ...form, title: event.target.value }))}
            />
          </label>
          <label className="field">
            <span>任务描述</span>
            <textarea
              className="input"
              rows={3}
              value={editForm.description}
              onChange={(event) =>
                setEditForm((form) => ({ ...form, description: event.target.value }))
              }
            />
          </label>
          <div className="field-grid two">
            <label className="field">
              <span>截止时间</span>
              <input
                className="input"
                placeholder="如 2026年11月20日，可留空"
                value={editForm.deadline}
                onChange={(event) =>
                  setEditForm((form) => ({ ...form, deadline: event.target.value }))
                }
              />
            </label>
            <label className="field">
              <span>优先级</span>
              <select
                className="select"
                value={editForm.priority}
                onChange={(event) =>
                  setEditForm((form) => ({ ...form, priority: event.target.value as TaskPriority }))
                }
              >
                <option value="high">高</option>
                <option value="medium">中</option>
                <option value="low">低</option>
              </select>
            </label>
          </div>
          {editError && (
            <div className="inline-error" role="alert">
              <AlertCircle size={15} />
              <span>{editError}</span>
            </div>
          )}
        </div>
      </Modal>

      <Modal
        open={deleting !== null}
        title="删除任务"
        description="删除后不可恢复，需要重新生成或手动创建。"
        onClose={() => (removing ? undefined : setDeleting(null))}
        footer={
          <>
            <Button variant="secondary" onClick={() => setDeleting(null)} disabled={removing}>
              取消
            </Button>
            <Button variant="primary" onClick={() => void handleDelete()} disabled={removing}>
              {removing ? '删除中…' : '确认删除'}
            </Button>
          </>
        }
      >
        <p className="muted-note">
          确定删除任务「{deleting?.title}」吗？该操作会直接删除 SQLite 中的记录。
        </p>
        {deleteError && (
          <div className="inline-error" role="alert">
            <AlertCircle size={15} />
            <span>{deleteError}</span>
          </div>
        )}
      </Modal>

      <Modal
        open={createOpen}
        title="新建任务"
        description="手动任务同样写入 SQLite，并需要归属一个已存在的事项。"
        onClose={() => (creating ? undefined : setCreateOpen(false))}
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => setCreateOpen(false)}
              disabled={creating}
            >
              取消
            </Button>
            <Button variant="primary" onClick={() => void handleCreate()} disabled={creating}>
              {creating ? '创建中…' : '创建任务'}
            </Button>
          </>
        }
      >
        <div className="form-grid">
          <label className="field">
            <span>所属事项 <em>*</em></span>
            <select
              className="select"
              value={createForm.matterId}
              onChange={(event) =>
                setCreateForm((form) => ({ ...form, matterId: event.target.value }))
              }
            >
              {matters.map((matter) => (
                <option key={matter.id} value={matter.id}>
                  #{matter.id} {matter.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>任务名称 <em>*</em></span>
            <input
              className="input"
              value={createForm.title}
              onChange={(event) =>
                setCreateForm((form) => ({ ...form, title: event.target.value }))
              }
            />
          </label>
          <label className="field">
            <span>任务描述</span>
            <textarea
              className="input"
              rows={3}
              value={createForm.description}
              onChange={(event) =>
                setCreateForm((form) => ({ ...form, description: event.target.value }))
              }
            />
          </label>
          <div className="field-grid two">
            <label className="field">
              <span>截止时间</span>
              <input
                className="input"
                placeholder="可留空"
                value={createForm.deadline}
                onChange={(event) =>
                  setCreateForm((form) => ({ ...form, deadline: event.target.value }))
                }
              />
            </label>
            <label className="field">
              <span>优先级</span>
              <select
                className="select"
                value={createForm.priority}
                onChange={(event) =>
                  setCreateForm((form) => ({
                    ...form,
                    priority: event.target.value as TaskPriority,
                  }))
                }
              >
                <option value="high">高</option>
                <option value="medium">中</option>
                <option value="low">低</option>
              </select>
            </label>
          </div>
          {createError && (
            <div className="inline-error" role="alert">
              <AlertCircle size={15} />
              <span>{createError}</span>
            </div>
          )}
        </div>
      </Modal>
    </div>
  )
}
