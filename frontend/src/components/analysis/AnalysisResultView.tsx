import {
  AlertCircle,
  AlertTriangle,
  BookmarkPlus,
  CheckCircle2,
  FileSearch,
  ListChecks,
  Route,
  Sparkles,
  StickyNote,
} from 'lucide-react'
import type { AnalysisResult, BadgeTone, Evidence } from '../../types'
import { formatFileSize } from '../../lib/format'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { SectionCard } from '../ui/Card'
import { FieldCard } from './FieldCard'

function EvidenceLine({ evidence }: { evidence: Evidence }) {
  return (
    <p className="evidence-line">
      来源：{evidence.location} ·「{evidence.text}」
    </p>
  )
}

const modeMeta: Record<AnalysisResult['analysis_mode'], { badge: string; title: string; tone: BadgeTone }> = {
  rule_based: { badge: '规则提取', title: '未配置大模型 · 本地规则结果', tone: 'neutral' },
  ai_assisted: { badge: 'AI 辅助 + 本地证据', title: '大模型辅助分析完成', tone: 'success' },
  rule_fallback: { badge: 'AI 未完成 · 规则回退', title: '本次已回退到本地规则结果', tone: 'warning' },
}

type AnalysisResultViewProps = {
  result: AnalysisResult
  savedMatterId?: number | null
  saving?: boolean
  saveError?: string
  onSave?: () => void
  onOpenMatters?: () => void
}

/** 解析结果：要素、材料、流程、注意事项与全部证据来源。 */
export function AnalysisResultView({
  result,
  savedMatterId = null,
  saving = false,
  saveError = '',
  onSave,
  onOpenMatters,
}: AnalysisResultViewProps) {
  const { document: doc } = result
  const mode = modeMeta[result.analysis_mode]
  const saved = savedMatterId !== null
  const positionText = doc.page_count
    ? `${doc.page_count} 页`
    : doc.paragraph_count
      ? `${doc.paragraph_count} 段 / 行`
      : '—'

  return (
    <div className="stack">
      <SectionCard
        title="解析结果"
        description={`文件已在后端真实读取，结果附本地原文证据；耗时 ${result.elapsed_ms} 毫秒`}
        action={<Badge tone={mode.tone}>{mode.badge}</Badge>}
      >
        <div className="doc-meta-grid">
          <div>
            <span>文件</span>
            <strong title={doc.filename}>{doc.filename}</strong>
          </div>
          <div>
            <span>大小</span>
            <strong>{formatFileSize(doc.size)}</strong>
          </div>
          <div>
            <span>文本量</span>
            <strong>{doc.char_count} 字符</strong>
          </div>
          <div>
            <span>位置信息</span>
            <strong>{positionText}</strong>
          </div>
          <div>
            <span>本地 OCR</span>
            <strong>{doc.ocr_used ? `第 ${doc.ocr_pages.join('、')} 页` : '未使用'}</strong>
          </div>
        </div>

        <div className={`ai-mode-box ${result.analysis_mode === 'ai_assisted' ? 'configured' : 'not-configured'}`}>
          <Sparkles size={16} />
          <div>
            <strong>{mode.title}</strong>
            <p>{result.ai_message}</p>
          </div>
        </div>

        {result.warnings.length > 0 && (
          <ul className="warning-list">
            {result.warnings.map((warning) => (
              <li key={warning}>
                <AlertTriangle size={14} />
                <span>{warning}</span>
              </li>
            ))}
          </ul>
        )}

        {saved ? (
          <div className="notice-bar">
            <CheckCircle2 size={16} />
            <span>
              已保存为事项 <strong>#{savedMatterId}</strong>，数据已写入本机 SQLite，刷新页面不会丢失。
            </span>
          </div>
        ) : (
          <div className="form-actions">
            <Button variant="primary" onClick={onSave} disabled={saving || !onSave}>
              <BookmarkPlus size={16} />
              {saving ? '正在保存…' : '保存为事项'}
            </Button>
            <span className="muted-note">事项、材料、流程、注意事项与原文证据会一并保存</span>
          </div>
        )}

        {saved && onOpenMatters && (
          <div className="form-actions">
            <Button variant="secondary" onClick={onOpenMatters}>
              前往我的事项
            </Button>
          </div>
        )}

        {saveError && (
          <div className="inline-error" role="alert">
            <AlertCircle size={15} />
            <span>{saveError}</span>
          </div>
        )}
      </SectionCard>

      <div className="extraction-legend">
        <div className="legend-head">
          <strong>提取结果可信度</strong>
          <span>{result.analysis_mode === 'ai_assisted' ? 'AI 提供候选值，本地原文提供证据' : '当前展示本地规则提取结果'}</span>
        </div>
        <ul className="legend-items">
          <li>
            <Badge tone="success">原文明确提取</Badge>
            <span>字段值可在原文中直接找到对应句子</span>
          </li>
          <li>
            <Badge tone="info">{result.analysis_mode === 'ai_assisted' ? '模型归纳' : '规则推断'}</Badge>
            <span>经过归纳但缺少可直接引用的原文句子，需人工确认</span>
          </li>
          <li>
            <Badge tone="warning">待核实</Badge>
            <span>识别到线索但信息不完整，需人工确认</span>
          </li>
          <li>
            <Badge tone="neutral">无法判断</Badge>
            <span>原文未提供有效信息，不能据此办理</span>
          </li>
        </ul>
      </div>

      <div className="field-grid">
        {result.fields.map((field) => (
          <FieldCard field={field} analysisMode={result.analysis_mode} key={field.key} />
        ))}
      </div>

      <div className="analysis-columns">
        <SectionCard
          title="所需材料"
          description="按原文材料清单逐条列出"
          action={<Badge tone="neutral">{result.materials.length} 项</Badge>}
        >
          {result.materials.length === 0 ? (
            <p className="empty-hint">
              未在原文中识别到材料清单。请核实文档是否包含「申请材料 / 所需材料」章节，或该事项无需提交材料。
            </p>
          ) : (
            <ul className="result-items">
              {result.materials.map((item, index) => (
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
        </SectionCard>

        <SectionCard
          title="办理流程"
          description="按原文流程顺序列出"
          action={<Badge tone="neutral">{result.process.length} 步</Badge>}
        >
          {result.process.length === 0 ? (
            <p className="empty-hint">
              未在原文中识别到办理流程。请核实文档是否包含「办理流程 / 办理步骤」章节。
            </p>
          ) : (
            <ol className="result-items">
              {result.process.map((step) => (
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
        </SectionCard>
      </div>

      <SectionCard
        title="注意事项"
        description="原文中的提示与限制条件"
        action={
          <span className="section-icon-note">
            <StickyNote size={15} />
            {result.notes.length} 条
          </span>
        }
      >
        {result.notes.length === 0 ? (
          <p className="empty-hint">
            未在原文中识别到注意事项。请核实文档是否包含「注意事项 / 温馨提示」章节。
          </p>
        ) : (
          <ul className="result-items">
            {result.notes.map((note, index) => (
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
      </SectionCard>

      <p className="muted-note">
        <FileSearch size={13} />
        以上为{result.analysis_mode === 'ai_assisted' ? ' AI 辅助分析' : '规则提取'}结果，不构成办事依据。
        原文证据用于追溯，不代表内容已经办理机构确认；归纳、待核实与无法判断的字段请以原文或办理机构答复为准。
      </p>
    </div>
  )
}
