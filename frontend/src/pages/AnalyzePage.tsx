import { useEffect, useState } from 'react'
import {
  AlertCircle,
  CheckCircle2,
  File,
  FileImage,
  FileText,
  FileType2,
  Info,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react'
import { AnalysisRequestError, analyzeDocument, fetchAnalysisCapabilities } from '../api/analysis'
import { createMatter, MatterRequestError } from '../api/matters'
import { AnalysisResultView } from '../components/analysis/AnalysisResultView'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { SectionCard } from '../components/ui/Card'
import { FileDropzone } from '../components/ui/FileDropzone'
import { PageHeader } from '../components/ui/PageHeader'
import { useToast } from '../components/ui/Toast'
import { formatFileSize } from '../lib/format'
import type { RouteKey } from '../hooks/useHashRoute'
import type { AnalysisCapabilities, AnalysisResult, MatterCreatePayload } from '../types'

const formatCards = [
  { icon: FileText, name: 'PDF', desc: '文本型通知及扫描 PDF（本地 OCR）' },
  { icon: FileType2, name: 'DOCX', desc: 'Word 文档、申请表、办事指南' },
  { icon: File, name: 'TXT', desc: '纯文本办事指南、材料清单' },
  { icon: FileImage, name: 'PNG / JPG', desc: '中文图片、截图（本地 OCR）' },
]

const steps = [
  { title: '上传文件', desc: 'PDF / DOCX / TXT / PNG / JPG / JPEG，单文件不超过 10MB' },
  { title: '读取文本', desc: '读取原生文本，图片和扫描页在本机执行 RapidOCR' },
  { title: '提取要素', desc: '已配置时调用大模型，并始终保留本地规则结果用于回退' },
  { title: '输出证据', desc: 'AI 只引用片段编号，证据正文和位置由后端从本地原文生成' },
]

const implemented = [
  'PDF / DOCX / TXT 文本读取与 PNG / JPG 本地 OCR',
  'OpenAI 兼容大模型辅助提取与严格证据校验',
  '规则结果预先生成，AI 失败时显式回退',
  '材料清单、流程、注意事项及原文位置定位',
]

const notImplemented = ['多文件批量分析与结果合并', '分析结果导出']

type UploadStatus = 'idle' | 'uploading' | 'parsing'

function buildMatterPayload(result: AnalysisResult): MatterCreatePayload {
  // 名称等字段直接取分析结果，不在这里硬编码任何文档答案。
  const fields = new Map(result.fields.map((field) => [field.key, field]))
  const valueOf = (key: string) => fields.get(key)?.value?.trim() ?? ''

  return {
    name: valueOf('title') || result.document.filename,
    matter_type: valueOf('matter_type'),
    qualification: valueOf('qualification'),
    registration_start: valueOf('registration_start') || null,
    deadline: valueOf('deadline') || null,
    deadline_source: valueOf('deadline') ? 'document' : 'none',
    materials: result.materials,
    process: result.process,
    notes: result.notes,
    fields: result.fields,
    source_filename: result.document.filename,
    status: 'pending',
    analysis_mode: result.analysis_mode,
  }
}

type AnalyzePageProps = {
  onNavigate?: (key: RouteKey) => void
}

export function AnalyzePage({ onNavigate }: AnalyzePageProps) {
  const [file, setFile] = useState<File | null>(null)
  const [status, setStatus] = useState<UploadStatus>('idle')
  const [progress, setProgress] = useState(0)
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [error, setError] = useState('')
  const [capabilities, setCapabilities] = useState<AnalysisCapabilities | null>(null)
  const [capabilityError, setCapabilityError] = useState('')
  const [savedMatterId, setSavedMatterId] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')
  const { showToast } = useToast()

  const busy = status !== 'idle'

  useEffect(() => {
    let active = true
    fetchAnalysisCapabilities()
      .then((data) => {
        if (!active) return
        setCapabilities(data)
        setCapabilityError('')
      })
      .catch((reason: unknown) => {
        if (!active) return
        setCapabilityError(
          reason instanceof Error ? reason.message : '无法读取分析能力状态，请确认后端服务是否正常。',
        )
      })
    return () => {
      active = false
    }
  }, [])

  const handleFiles = (incoming: File[]) => {
    if (busy) return
    setFile(incoming[0] ?? null)
    setResult(null)
    setError('')
    setProgress(0)
    setSavedMatterId(null)
    setSaveError('')
  }

  const clearFile = () => {
    if (busy) return
    setFile(null)
    setResult(null)
    setError('')
    setProgress(0)
    setSavedMatterId(null)
    setSaveError('')
  }

  const handleStart = async () => {
    if (!file || busy) {
      if (!file) showToast('请先选择需要分析的材料文件。', 'warning')
      return
    }

    setStatus('uploading')
    setProgress(0)
    setResult(null)
    setError('')
    setSavedMatterId(null)
    setSaveError('')

    try {
      const data = await analyzeDocument(file, {
        onProgress: setProgress,
        onUploaded: () => setStatus('parsing'),
      })
      setResult(data)
      showToast(`解析完成，用时 ${data.elapsed_ms} 毫秒。`, 'success')
    } catch (reason) {
      const message =
        reason instanceof AnalysisRequestError
          ? reason.message
          : '分析失败，请稍后重试或更换文件。'
      setError(message)
      showToast(message, 'warning')
    } finally {
      setStatus('idle')
    }
  }

  const handleSave = async () => {
    if (!result || saving || savedMatterId !== null) return

    setSaving(true)
    setSaveError('')
    try {
      const saved = await createMatter(buildMatterPayload(result))
      setSavedMatterId(saved.id)
      showToast(`已保存为事项 #${saved.id}，可在「我的事项」查看。`, 'success')
    } catch (reason) {
      const message =
        reason instanceof MatterRequestError ? reason.message : '保存事项失败，请稍后重试。'
      setSaveError(message)
      showToast(message, 'warning')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="智能分析"
        description="上传办事文档或图片，本地 OCR 读取文字，AI 与规则提取事项要素并附原文证据。"
        badge={<Badge tone="info">AI + 本地 OCR</Badge>}
      />

      {capabilityError ? (
        <div className="notice-bar warning">
          <AlertCircle size={16} />
          <span>{capabilityError}</span>
        </div>
      ) : (
        capabilities && (
          <div className={`notice-bar ${capabilities.ai_configured ? '' : 'warning'}`}>
            <Info size={16} />
            <span>
              <strong>
                {capabilities.ai_configured
                  ? '当前优先模式：AI 辅助分析（ai_assisted）。'
                  : '当前分析模式：本地规则提取（rule_based）。'}
              </strong>
              {capabilities.ai_message}
              <br />
              <strong>本地 OCR：</strong>{capabilities.ocr_message}
            </span>
          </div>
        )
      )}

      <div className="analyze-grid">
        <div className="stack">
          <SectionCard
            title="上传材料"
            description="每次分析一个文件，拖拽到虚线区域内或点击选择"
            action={<Badge tone="neutral">单文件 ≤ 10MB</Badge>}
          >
            <FileDropzone
              onFiles={handleFiles}
              multiple={false}
              hint="支持 PDF / DOCX / TXT / PNG / JPG / JPEG，单个文件不超过 10MB"
              note={capabilities?.ai_configured
                ? '文档文本会发送到所配置模型服务；图片与扫描页的 OCR 仅在本机执行'
                : '文件上传到本机后端；未配置 AI，不发送第三方模型服务；OCR 仅在本机执行'}
            />

            {file && (
              <>
                <div className="file-list-head">
                  <span>待分析文件</span>
                  <button type="button" className="link-btn" onClick={clearFile} disabled={busy}>
                    <Trash2 size={13} />
                    移除
                  </button>
                </div>
                <ul className="file-list">
                  <li className="file-row">
                    <span className="row-icon">
                      <FileText size={16} />
                    </span>
                    <div className="file-main">
                      <strong>{file.name}</strong>
                      <small>{formatFileSize(file.size)} · 点击「开始智能分析」后上传</small>
                    </div>
                    <button
                      type="button"
                      className="icon-btn"
                      aria-label={`移除 ${file.name}`}
                      onClick={clearFile}
                      disabled={busy}
                    >
                      <X size={16} />
                    </button>
                  </li>
                </ul>
              </>
            )}

            {busy && (
              <div className="upload-progress" role="status" aria-live="polite">
                <div className="progress-head">
                  <span>
                    {status === 'uploading' ? '正在上传文件…' : '上传完成，正在 OCR / 规则 / AI 分析…'}
                  </span>
                  <span>{status === 'uploading' ? `${progress}%` : '解析中'}</span>
                </div>
                <div className="progress-track">
                  <div
                    className={`progress-fill ${status === 'parsing' ? 'indeterminate' : ''}`.trim()}
                    style={status === 'uploading' ? { width: `${progress}%` } : undefined}
                  />
                </div>
              </div>
            )}

            {error && (
              <div className="inline-error analysis-error" role="alert">
                <AlertCircle size={15} />
                <span>{error}</span>
              </div>
            )}

            <div className="form-actions">
              <Button variant="accent" onClick={handleStart} disabled={!file || busy}>
                <Sparkles size={16} />
                {status === 'uploading'
                  ? '正在上传…'
                  : status === 'parsing'
                    ? '正在解析…'
                    : '开始智能分析'}
              </Button>
              <span className="muted-note">
                {file
                  ? busy
                    ? '请等待分析完成，不要关闭页面'
                    : '将真实上传并解析该文件'
                  : '请先选择一个文件'}
              </span>
            </div>
          </SectionCard>

          <SectionCard title="分析流程" description="以下四个步骤均已接入真实后端">
            <ol className="step-list">
              {steps.map((step, index) => (
                <li className="step-item" key={step.title}>
                  <span className="step-index">{String(index + 1).padStart(2, '0')}</span>
                  <div>
                    <strong>{step.title}</strong>
                    <p>{step.desc}</p>
                  </div>
                  <Badge tone="success">已实现</Badge>
                </li>
              ))}
            </ol>
          </SectionCard>
        </div>

        <div className="stack">
          <SectionCard
            title="支持的文件格式"
            description="后端会校验格式、空文件与异常文档"
          >
            <ul className="format-list">
              {formatCards.map(({ icon: Icon, name, desc }) => (
                <li className="format-row" key={name}>
                  <span className="row-icon">
                    <Icon size={17} />
                  </span>
                  <div>
                    <strong>{name}</strong>
                    <p>{desc}</p>
                  </div>
                </li>
              ))}
            </ul>
            <p className="muted-note">
              文件大小上限 {capabilities?.max_upload_mb ?? 10}MB；图片与扫描 PDF 使用本地 OCR，
              OCR 页数和失败页会在结果中明确展示。
            </p>
          </SectionCard>

          <SectionCard title="分析能力" description="实际使用的模式以每次结果标识为准">
            <div className="capability-block">
              <strong className="capability-title">
                <CheckCircle2 size={14} />
                已实现
              </strong>
              <ul className="plain-list">
                {implemented.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
            <div className="capability-block muted">
              <strong className="capability-title">
                <AlertCircle size={14} />
                尚未实现
              </strong>
              <ul className="plain-list warning">
                {notImplemented.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          </SectionCard>
        </div>
      </div>

      {result && (
        <AnalysisResultView
          result={result}
          savedMatterId={savedMatterId}
          saving={saving}
          saveError={saveError}
          onSave={handleSave}
          onOpenMatters={onNavigate ? () => onNavigate('matters') : undefined}
        />
      )}
    </div>
  )
}
