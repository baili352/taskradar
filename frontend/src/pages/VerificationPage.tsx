import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertCircle,
  CheckCircle2,
  FileText,
  Info,
  Pencil,
  Plus,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Trash2,
  Upload,
} from 'lucide-react'
import { fetchMatters } from '../api/matters'
import {
  confirmMaterial,
  createMaterial,
  deleteMaterial,
  fetchMaterialProgress,
  fetchMaterials,
  generateMaterials,
  materialErrorMessage,
  updateMaterial,
  uploadMaterialFile,
  verifyMaterial,
} from '../api/materials'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { SectionCard } from '../components/ui/Card'
import { Modal } from '../components/ui/Modal'
import { PageHeader } from '../components/ui/PageHeader'
import { useToast } from '../components/ui/Toast'
import { formatDateTime, formatFileSize } from '../lib/format'
import { materialRecordStatusMeta } from '../lib/meta'
import type {
  BadgeTone,
  MaterialCheckStatus,
  MaterialProgress,
  MaterialRecord,
  MaterialRecordStatus,
  MaterialVerificationResult,
  MatterRecord,
} from '../types'

const MAX_FILE_BYTES = 10 * 1024 * 1024
const ALLOWED_EXTENSIONS = ['pdf', 'docx', 'txt', 'png', 'jpg', 'jpeg']

const statusFilters: { value: 'all' | MaterialRecordStatus; label: string }[] = [
  { value: 'all', label: '全部状态' },
  { value: 'missing', label: '未提供' },
  { value: 'pending', label: '待核验' },
  { value: 'qualified', label: '已确认' },
  { value: 'incomplete', label: '信息不完整' },
  { value: 'conflict', label: '存在冲突' },
  { value: 'uncertain', label: '无法判断' },
]

const confirmOptions: { value: MaterialVerificationResult; label: string }[] = [
  { value: 'qualified', label: '已确认符合' },
  { value: 'incomplete', label: '信息不完整' },
  { value: 'conflict', label: '存在冲突' },
  { value: 'uncertain', label: '无法判断' },
]

const checkTone: Record<MaterialCheckStatus, BadgeTone> = {
  pass: 'success',
  warn: 'warning',
  unknown: 'neutral',
}

const checkLabel: Record<MaterialCheckStatus, string> = {
  pass: '通过',
  warn: '待确认',
  unknown: '无法判断',
}

const eventLabels: Record<string, string> = {
  created: '手动新增',
  generated: '流程生成',
  updated: '修改材料',
  file_uploaded: '上传文件',
  verified: '规则核验',
  confirmed: '人工确认',
}

type VerificationPageProps = {
  focusMatterId?: number
  focusMaterialId?: number
}

export function VerificationPage({ focusMatterId, focusMaterialId }: VerificationPageProps) {
  const [matters, setMatters] = useState<MatterRecord[]>([])
  const [matterFilter, setMatterFilter] = useState(
    focusMatterId ? String(focusMatterId) : 'all',
  )
  const focusApplied = useRef(false)
  const [statusFilter, setStatusFilter] = useState<'all' | MaterialRecordStatus>('all')
  const [materials, setMaterials] = useState<MaterialRecord[]>([])
  const [progress, setProgress] = useState<MaterialProgress | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [generating, setGenerating] = useState(false)
  const [uploadingId, setUploadingId] = useState<number | null>(null)
  const [verifyingId, setVerifyingId] = useState<number | null>(null)

  const [detail, setDetail] = useState<MaterialRecord | null>(null)
  const [confirmStatus, setConfirmStatus] = useState<MaterialVerificationResult | ''>('')
  const [confirmNote, setConfirmNote] = useState('')
  const [confirmEvidence, setConfirmEvidence] = useState('')
  const [confirmError, setConfirmError] = useState('')
  const [confirming, setConfirming] = useState(false)

  const [createOpen, setCreateOpen] = useState(false)
  const [createForm, setCreateForm] = useState({ matterId: '', name: '', description: '' })
  const [createError, setCreateError] = useState('')
  const [creating, setCreating] = useState(false)

  const [editing, setEditing] = useState<MaterialRecord | null>(null)
  const [editForm, setEditForm] = useState({ name: '', description: '' })
  const [editError, setEditError] = useState('')
  const [saving, setSaving] = useState(false)

  const [deleting, setDeleting] = useState<MaterialRecord | null>(null)
  const [deleteError, setDeleteError] = useState('')
  const [removing, setRemoving] = useState(false)

  const { showToast } = useToast()

  const loadMatters = useCallback(async () => {
    try {
      setMatters(await fetchMatters())
    } catch (reason) {
      showToast(materialErrorMessage(reason, '读取事项列表失败，请确认后端服务是否正常。'), 'warning')
    }
  }, [showToast])

  const loadMaterials = useCallback(async () => {
    setLoading(true)
    setLoadError('')
    try {
      const matterId = matterFilter === 'all' ? undefined : Number(matterFilter)
      const list = await fetchMaterials({
        matterId,
        status: statusFilter === 'all' ? undefined : statusFilter,
      })
      setMaterials(list)
      if (matterId) {
        setProgress(await fetchMaterialProgress(matterId))
      } else {
        setProgress(null)
      }
    } catch (reason) {
      setLoadError(materialErrorMessage(reason, '读取材料清单失败，请确认后端服务是否正常。'))
    } finally {
      setLoading(false)
    }
  }, [matterFilter, statusFilter])

  useEffect(() => {
    void loadMatters()
  }, [loadMatters])

  useEffect(() => {
    void loadMaterials()
  }, [loadMaterials])

  useEffect(() => {
    if (focusApplied.current || !focusMaterialId) return
    const target = materials.find((material) => material.id === focusMaterialId)
    if (!target) return
    focusApplied.current = true
    openDetail(target)
  }, [focusMaterialId, materials])

  const applyUpdate = useCallback(
    (updated: MaterialRecord) => {
      setMaterials((current) => {
        const exists = current.some((item) => item.id === updated.id)
        if (statusFilter !== 'all' && updated.status !== statusFilter) {
          return exists ? current.filter((item) => item.id !== updated.id) : current
        }
        return exists
          ? current.map((item) => (item.id === updated.id ? updated : item))
          : [updated, ...current]
      })
      setDetail((current) => (current && current.id === updated.id ? updated : current))
    },
    [statusFilter],
  )

  const refreshProgress = useCallback(async () => {
    if (matterFilter === 'all') {
      setProgress(null)
      return
    }
    try {
      setProgress(await fetchMaterialProgress(Number(matterFilter)))
    } catch {
      /* 进度失败不阻断主要操作 */
    }
  }, [matterFilter])

  const openDetail = (material: MaterialRecord) => {
    setDetail(material)
    // 人工确认必须由用户主动选择，绝不默认「已确认符合」。
    setConfirmStatus('')
    setConfirmNote('')
    setConfirmEvidence('')
    setConfirmError('')
  }

  const handleGenerate = async () => {
    if (matterFilter === 'all' || generating) return
    setGenerating(true)
    try {
      const result = await generateMaterials(Number(matterFilter))
      showToast(result.message, result.created > 0 ? 'success' : 'warning')
      await loadMaterials()
    } catch (reason) {
      showToast(materialErrorMessage(reason, '生成材料清单失败，请稍后重试。'), 'warning')
    } finally {
      setGenerating(false)
    }
  }

  const handleUpload = async (material: MaterialRecord, file: File | undefined) => {
    if (!file) return
    const extension = file.name.toLowerCase().split('.').pop() ?? ''
    if (!ALLOWED_EXTENSIONS.includes(extension)) {
      showToast('仅支持 PDF、DOCX、TXT、PNG、JPG、JPEG 文件。', 'warning')
      return
    }
    if (file.size === 0) {
      showToast('文件内容为空，请重新选择。', 'warning')
      return
    }
    if (file.size > MAX_FILE_BYTES) {
      showToast('文件超过 10MB 限制，请压缩后重试。', 'warning')
      return
    }

    setUploadingId(material.id)
    try {
      const updated = await uploadMaterialFile(material.id, file)
      applyUpdate(updated)
      showToast(`已上传「${updated.original_filename}」，状态更新为待核验。`, 'success')
      await refreshProgress()
    } catch (reason) {
      showToast(materialErrorMessage(reason, '上传文件失败，请稍后重试。'), 'warning')
    } finally {
      setUploadingId(null)
    }
  }

  const handleVerify = async (material: MaterialRecord) => {
    if (verifyingId !== null) return
    setVerifyingId(material.id)
    try {
      const updated = await verifyMaterial(material.id)
      applyUpdate(updated)
      const label = materialRecordStatusMeta[updated.status].label
      showToast(`规则核验完成：${label}。依据与原文摘录已保存。`, 'success')
      openDetail(updated)
      await refreshProgress()
    } catch (reason) {
      showToast(materialErrorMessage(reason, '执行核验失败，请稍后重试。'), 'warning')
    } finally {
      setVerifyingId(null)
    }
  }

  const handleConfirm = async () => {
    if (!detail || confirming) return
    if (!confirmStatus) {
      setConfirmError('请先选择人工核验结果，再保存确认。')
      return
    }
    const note = confirmNote.trim()
    if (!note) {
      setConfirmError('请填写确认说明，记录人工核对的依据或情况。')
      return
    }
    setConfirming(true)
    setConfirmError('')
    try {
      const updated = await confirmMaterial(detail.id, {
        status: confirmStatus,
        note,
        evidence_text: confirmEvidence.trim() || null,
      })
      applyUpdate(updated)
      openDetail(updated)
      showToast('人工确认结果已保存。', 'success')
      await refreshProgress()
    } catch (reason) {
      const message = materialErrorMessage(reason, '保存人工确认失败，请稍后重试。')
      setConfirmError(message)
      showToast(message, 'warning')
    } finally {
      setConfirming(false)
    }
  }

  const openCreate = () => {
    setCreateForm({
      matterId: matterFilter !== 'all' ? matterFilter : matters[0] ? String(matters[0].id) : '',
      name: '',
      description: '',
    })
    setCreateError('')
    setCreateOpen(true)
  }

  const handleCreate = async () => {
    if (creating) return
    if (!createForm.matterId) {
      setCreateError('请选择材料所属事项。')
      return
    }
    const name = createForm.name.trim()
    if (!name) {
      setCreateError('请填写材料名称。')
      return
    }
    setCreating(true)
    setCreateError('')
    try {
      const created = await createMaterial(Number(createForm.matterId), {
        name,
        description: createForm.description.trim(),
      })
      setCreateOpen(false)
      showToast(`已新增材料「${created.name}」，当前状态为未提供。`, 'success')
      if (matterFilter === 'all' || createForm.matterId === matterFilter) {
        applyUpdate(created)
      } else {
        setMatterFilter(createForm.matterId)
      }
      await refreshProgress()
    } catch (reason) {
      const message = materialErrorMessage(reason, '新增材料失败，请稍后重试。')
      setCreateError(message)
      showToast(message, 'warning')
    } finally {
      setCreating(false)
    }
  }

  const openEdit = (material: MaterialRecord) => {
    setEditing(material)
    setEditForm({ name: material.name, description: material.description })
    setEditError('')
  }

  const handleEdit = async () => {
    if (!editing || saving) return
    const name = editForm.name.trim()
    if (!name) {
      setEditError('材料名称不能为空。')
      return
    }
    setSaving(true)
    setEditError('')
    try {
      const updated = await updateMaterial(editing.id, {
        name,
        description: editForm.description.trim(),
      })
      setEditing(null)
      applyUpdate(updated)
      showToast('材料信息已更新。', 'success')
    } catch (reason) {
      const message = materialErrorMessage(reason, '更新材料失败，请稍后重试。')
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
      await deleteMaterial(deleting.id)
      setMaterials((current) => current.filter((item) => item.id !== deleting.id))
      setDetail((current) => (current && current.id === deleting.id ? null : current))
      setDeleting(null)
      showToast('材料已删除，对应文件已从受控目录清理。', 'success')
      await refreshProgress()
    } catch (reason) {
      const message = materialErrorMessage(reason, '删除材料失败，请稍后重试。')
      setDeleteError(message)
      showToast(message, 'warning')
    } finally {
      setRemoving(false)
    }
  }

  const selectedMatter = useMemo(
    () => matters.find((matter) => String(matter.id) === matterFilter) ?? null,
    [matters, matterFilter],
  )

  const attentionCount = progress
    ? progress.incomplete + progress.conflict + progress.uncertain
    : 0

  return (
    <div className="page-stack">
      <PageHeader
        title="材料核验"
        description="材料清单与核验记录来自本机 SQLite，支持文档与图片上传、本地 OCR 和规则核验。"
        badge={<Badge tone="success">本机数据</Badge>}
        actions={
          <>
            <Button variant="secondary" onClick={() => void loadMaterials()} disabled={loading}>
              <RefreshCw size={16} />
              刷新
            </Button>
            <Button variant="primary" onClick={openCreate} disabled={matters.length === 0}>
              <Plus size={16} />
              新增材料
            </Button>
          </>
        }
      />

      <div className="notice-bar">
        <Info size={16} />
        <span>
          规则核验只依据文件文本与材料要求原文：不会仅凭文件名判定合格，也不会把上传成功等同于材料符合要求；
          无法判断时会标记为「无法判断」，发现可能问题时提示人工确认，系统不直接判定材料无效。
        </span>
      </div>

      <SectionCard
        title="材料清单"
        description={`数据来源：SQLite · 当前显示 ${materials.length} 项${
          selectedMatter ? ` · 所属事项：${selectedMatter.name}` : ''
        }`}
        action={
          <Button
            variant="accent"
            size="sm"
            onClick={() => void handleGenerate()}
            disabled={matterFilter === 'all' || generating}
          >
            <Sparkles size={15} />
            {generating ? '生成中…' : '生成材料清单'}
          </Button>
        }
      >
        <div className="toolbar">
          <select
            className="select"
            aria-label="按事项筛选"
            value={matterFilter}
            onChange={(event) => setMatterFilter(event.target.value)}
          >
            <option value="all">全部事项</option>
            {matters.map((matter) => (
              <option key={matter.id} value={String(matter.id)}>
                {matter.name}
              </option>
            ))}
          </select>
          <select
            className="select"
            aria-label="按状态筛选"
            value={statusFilter}
            onChange={(event) =>
              setStatusFilter(event.target.value as 'all' | MaterialRecordStatus)
            }
          >
            {statusFilters.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
          {matterFilter === 'all' && (
            <span className="muted-note">选择具体事项后，可生成材料清单并查看准备进度。</span>
          )}
        </div>

        {progress && (
          <div className="verify-summary">
            <div className="verify-progress">
              <div className="verify-progress-head">
                <span>材料准备进度（已提供 {progress.provided}/{progress.total}）</span>
                <strong>{progress.prepared_percent}%</strong>
              </div>
              <div className="progress">
                <span style={{ width: `${progress.prepared_percent}%` }} />
              </div>
              <div className="verify-progress-head" style={{ marginTop: 8 }}>
                <span>已确认符合 {progress.qualified} 项</span>
                <span>{progress.verified_percent}%</span>
              </div>
              <div className="progress">
                <span
                  style={{ width: `${progress.verified_percent}%`, background: 'var(--green-600)' }}
                />
              </div>
            </div>
            <div className="verify-counts">
              <span className="count success">已提供 {progress.provided}</span>
              <span className="count warning">待核验 {progress.pending}</span>
              <span className="count success">已确认 {progress.qualified}</span>
              <span className="count warning">需关注 {attentionCount}</span>
              <span className="count danger">未提供 {progress.missing}</span>
            </div>
          </div>
        )}

        {loadError && (
          <div className="notice-bar warning">
            <AlertCircle size={16} />
            <span>{loadError}</span>
          </div>
        )}

        {loading ? (
          <p className="muted-note">正在读取材料清单…</p>
        ) : materials.length === 0 ? (
          <div className="empty-state">
            <FileText size={26} />
            <p>
              {matterFilter === 'all'
                ? '暂无材料记录。请选择具体事项后生成材料清单，或手动新增材料。'
                : '该事项还没有材料记录。点击右上角「生成材料清单」，或手动新增。'}
            </p>
          </div>
        ) : (
          <ul className="material-list">
            {materials.map((material) => {
              const status = materialRecordStatusMeta[material.status]
              return (
                <li className="material-row" key={material.id}>
                  <span className="row-icon">
                    <FileText size={16} />
                  </span>
                  <div className="material-main">
                    <strong>
                      <span className="name-with-badge">
                        {material.name}
                        {material.is_demo && <Badge tone="demo">演示数据</Badge>}
                      </span>
                      <span className="optional-tag">
                        {material.origin === 'generated' ? '流程生成' : '手动添加'}
                      </span>
                    </strong>
                    <small>
                      {material.matter_name} ·{' '}
                      {material.original_filename
                        ? `${material.original_filename} · ${
                            material.file_size ? formatFileSize(material.file_size) : ''
                          }`
                        : '尚未上传材料'}
                    </small>
                    {material.verification && (
                      <small title={material.verification.summary}>
                        {material.verification.source === 'manual' ? '人工确认' : '规则核验'}：
                        {material.verification.summary}
                      </small>
                    )}
                  </div>
                  <Badge tone={status.tone}>{status.label}</Badge>
                  <div className="material-actions">
                    <label className="btn btn-secondary btn-sm upload-label">
                      <Upload size={14} />
                      {uploadingId === material.id
                        ? '上传中…'
                        : material.file_path
                          ? '重新上传'
                          : '上传'}
                      <input
                        type="file"
                        className="hidden-input"
                        accept=".pdf,.docx,.txt,.png,.jpg,.jpeg"
                        disabled={uploadingId === material.id}
                        onChange={(event) => {
                          void handleUpload(material, event.target.files?.[0])
                          event.target.value = ''
                        }}
                      />
                    </label>
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={() => void handleVerify(material)}
                      disabled={!material.file_path || verifyingId !== null}
                    >
                      <ShieldCheck size={14} />
                      {verifyingId === material.id ? '核验中…' : '核验'}
                    </Button>
                    <button
                      type="button"
                      className="icon-btn"
                      aria-label={`查看 ${material.name} 详情`}
                      onClick={() => openDetail(material)}
                    >
                      <Info size={15} />
                    </button>
                    <button
                      type="button"
                      className="icon-btn"
                      aria-label={`编辑 ${material.name}`}
                      onClick={() => openEdit(material)}
                    >
                      <Pencil size={15} />
                    </button>
                    <button
                      type="button"
                      className="icon-btn"
                      aria-label={`删除 ${material.name}`}
                      onClick={() => {
                        setDeleteError('')
                        setDeleting(material)
                      }}
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </SectionCard>

      {/* 材料详情与核验依据 */}
      <Modal
        open={detail !== null}
        title={detail ? `材料详情 · ${detail.name}` : '材料详情'}
        description="核验依据、原文摘录与操作记录均来自数据库，可人工确认或修改核验状态。"
        onClose={() => setDetail(null)}
        footer={
          <Button variant="secondary" onClick={() => setDetail(null)}>
            关闭
          </Button>
        }
      >
        {detail && (
          <div className="form-grid">
            <dl className="detail-list">
              <div>
                <dt>所属事项</dt>
                <dd>{detail.matter_name}</dd>
              </div>
              <div>
                <dt>当前状态</dt>
                <dd>
                  <Badge tone={materialRecordStatusMeta[detail.status].tone}>
                    {materialRecordStatusMeta[detail.status].label}
                  </Badge>
                </dd>
              </div>
              <div>
                <dt>文件</dt>
                <dd>{detail.original_filename ?? '尚未上传'}</dd>
              </div>
              <div>
                <dt>文件大小 / 类型</dt>
                <dd>
                  {detail.file_size ? formatFileSize(detail.file_size) : '—'} /{' '}
                  {detail.file_type ?? '—'}
                </dd>
              </div>
              <div>
                <dt>来源</dt>
                <dd>{detail.origin === 'generated' ? '事项材料要求生成' : '手动添加'}</dd>
              </div>
            </dl>

            {detail.description && (
              <div className="verification-box">
                <strong>材料要求</strong>
                <p>{detail.description}</p>
              </div>
            )}

            {detail.source_evidence && (
              <div className="verification-box">
                <strong>原文证据</strong>
                <p className="evidence-line">
                  来源：{detail.source_evidence.location} ·「{detail.source_evidence.text}」
                </p>
              </div>
            )}

            {detail.verification ? (
              <div className="verification-box">
                <div className="check-head">
                  <strong>核验记录</strong>
                  <Badge tone={detail.verification.source === 'manual' ? 'info' : 'neutral'}>
                    {detail.verification.source === 'manual' ? '人工确认' : '规则核验'}
                  </Badge>
                </div>
                <p>{detail.verification.summary}</p>
                <p className="muted-note">
                  核验时间：{formatDateTime(detail.verification.verified_at)}
                </p>
                <ul className="check-list">
                  {detail.verification.checks.map((check) => (
                    <li className="check-item" key={`${check.key}-${check.label}`}>
                      <div className="check-head">
                        <span>{check.label}</span>
                        <Badge tone={checkTone[check.status]}>
                          {checkLabel[check.status]}
                        </Badge>
                      </div>
                      <p>{check.message}</p>
                      {check.excerpt && (
                        <p className="check-excerpt">
                          摘录{check.location ? `（${check.location}）` : ''}：{check.excerpt}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
                {detail.verification.reasons.length > 0 && (
                  <div className="notice-bar warning">
                    <AlertCircle size={15} />
                    <span>需人工确认：{detail.verification.reasons.join('；')}</span>
                  </div>
                )}
              </div>
            ) : (
              <div className="verification-box">
                <strong>核验记录</strong>
                <p className="muted-note">尚未执行核验。上传文件后点击「核验」生成规则核验记录。</p>
              </div>
            )}

            {detail.file_path && (
              <div className="verification-box">
                <strong>人工确认核验结果</strong>
                <div className="notice-bar">
                  <Info size={15} />
                  <span>
                    上方「规则核验」只依据文件文本与材料要求给出关键词线索，不代表材料真实性的证明，
                    也不具备法律效力；
                    下方结论需要你主动选择并填写说明，保存后会作为人工确认记录保留。
                  </span>
                </div>
                <div className="field">
                  <span>
                    确认状态 <em>*</em>
                  </span>
                  <select
                    className="select"
                    value={confirmStatus}
                    onChange={(event) =>
                      setConfirmStatus(event.target.value as MaterialVerificationResult | '')
                    }
                  >
                    <option value="" disabled>
                      请选择核验结果（必选）
                    </option>
                    {confirmOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <span>
                    确认说明 <em>*</em>
                  </span>
                  <textarea
                    className="input"
                    placeholder="例如：已核对原件，签字与日期齐全。"
                    value={confirmNote}
                    onChange={(event) => setConfirmNote(event.target.value)}
                  />
                </div>
                <div className="field">
                  <span>补充原文摘录（选填）</span>
                  <textarea
                    className="input"
                    placeholder="可粘贴人工核对时依据的原文。"
                    value={confirmEvidence}
                    onChange={(event) => setConfirmEvidence(event.target.value)}
                  />
                </div>
                {confirmError && (
                  <div className="inline-error" role="alert">
                    <AlertCircle size={15} />
                    <span>{confirmError}</span>
                  </div>
                )}
                <div className="check-head">
                  <span className="muted-note">人工确认会保留操作记录，并覆盖当前核验状态。</span>
                  <Button
                    variant="accent"
                    size="sm"
                    onClick={() => void handleConfirm()}
                    disabled={confirming || !confirmStatus}
                  >
                    <CheckCircle2 size={14} />
                    {confirming ? '保存中…' : '保存人工确认'}
                  </Button>
                </div>
              </div>
            )}

            {detail.events.length > 0 && (
              <div className="verification-box">
                <strong>操作记录</strong>
                <ul className="event-list">
                  {detail.events.map((event) => (
                    <li key={event.id}>
                      <span>{eventLabels[event.action] ?? event.action}</span>
                      <small>{formatDateTime(event.created_at)}</small>
                      <p>{event.detail}</p>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </Modal>

      {/* 新增材料 */}
      <Modal
        open={createOpen}
        title="新增材料"
        description="手动添加的材料同样写入 SQLite，状态为「未提供」，上传文件后转为「待核验」。"
        onClose={() => {
          if (!creating) setCreateOpen(false)
        }}
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
              {creating ? '保存中…' : '保存材料'}
            </Button>
          </>
        }
      >
        <div className="form-grid">
          <label className="field">
            <span>
              所属事项 <em>*</em>
            </span>
            <select
              className="select"
              value={createForm.matterId}
              onChange={(event) =>
                setCreateForm((current) => ({ ...current, matterId: event.target.value }))
              }
            >
              <option value="">请选择事项</option>
              {matters.map((matter) => (
                <option key={matter.id} value={String(matter.id)}>
                  {matter.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>
              材料名称 <em>*</em>
            </span>
            <input
              className="input"
              value={createForm.name}
              maxLength={200}
              placeholder="例如：报名表"
              onChange={(event) =>
                setCreateForm((current) => ({ ...current, name: event.target.value }))
              }
            />
          </label>
          <label className="field">
            <span>要求说明</span>
            <textarea
              className="input"
              value={createForm.description}
              maxLength={2000}
              placeholder="例如：需本人签字并加盖公章"
              onChange={(event) =>
                setCreateForm((current) => ({ ...current, description: event.target.value }))
              }
            />
          </label>
          {createError && (
            <div className="inline-error" role="alert">
              <AlertCircle size={15} />
              <span>{createError}</span>
            </div>
          )}
        </div>
      </Modal>

      {/* 编辑材料 */}
      <Modal
        open={editing !== null}
        title="编辑材料"
        description="修改材料名称与要求说明，不会影响已上传文件与核验记录。"
        onClose={() => {
          if (!saving) setEditing(null)
        }}
        footer={
          <>
            <Button variant="secondary" onClick={() => setEditing(null)} disabled={saving}>
              取消
            </Button>
            <Button variant="primary" onClick={() => void handleEdit()} disabled={saving}>
              {saving ? '保存中…' : '保存修改'}
            </Button>
          </>
        }
      >
        <div className="form-grid">
          <label className="field">
            <span>
              材料名称 <em>*</em>
            </span>
            <input
              className="input"
              value={editForm.name}
              maxLength={200}
              onChange={(event) =>
                setEditForm((current) => ({ ...current, name: event.target.value }))
              }
            />
          </label>
          <label className="field">
            <span>要求说明</span>
            <textarea
              className="input"
              value={editForm.description}
              maxLength={2000}
              onChange={(event) =>
                setEditForm((current) => ({ ...current, description: event.target.value }))
              }
            />
          </label>
          {editError && (
            <div className="inline-error" role="alert">
              <AlertCircle size={15} />
              <span>{editError}</span>
            </div>
          )}
        </div>
      </Modal>

      {/* 删除确认 */}
      <Modal
        open={deleting !== null}
        title="删除材料"
        description="删除后材料记录与受控目录中的对应文件都会被清理，且不可恢复。"
        onClose={() => {
          if (!removing) setDeleting(null)
        }}
        footer={
          <>
            <Button variant="secondary" onClick={() => setDeleting(null)} disabled={removing}>
              取消
            </Button>
            <Button
              variant="primary"
              className="btn-danger"
              onClick={() => void handleDelete()}
              disabled={removing}
            >
              {removing ? '删除中…' : '确认删除'}
            </Button>
          </>
        }
      >
        <p>
          确认删除材料「<strong>{deleting?.name}</strong>」吗？该操作会同时删除已上传文件。
        </p>
        {deleteError && (
          <div className="inline-error" role="alert">
            <AlertCircle size={15} />
            <span>{deleteError}</span>
          </div>
        )}
      </Modal>
    </div>
  )
}
