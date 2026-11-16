import type { AnalysisField, AnalysisResult } from '../../types'
import { Badge } from '../ui/Badge'
import { EvidenceList } from './EvidenceList'

const stateMeta = {
  exact: { label: '原文明确提取', tone: 'success' as const },
  inferred: { label: '规则推断', tone: 'info' as const },
  pending: { label: '待核实', tone: 'warning' as const },
  unknown: { label: '无法判断', tone: 'neutral' as const },
}

/** 根据字段状态与证据情况区分四种提取可信度，避免把规则推断当成原文事实。 */
function fieldState(field: AnalysisField, analysisMode: AnalysisResult['analysis_mode']) {
  const hasValue = Boolean(field.value && field.value.trim())
  if (field.status === 'found') {
    if (field.evidence.length > 0) return stateMeta.exact
    return analysisMode === 'ai_assisted'
      ? { ...stateMeta.inferred, label: '模型归纳' }
      : stateMeta.inferred
  }
  return hasValue ? stateMeta.pending : stateMeta.unknown
}

/** 单个事项要素卡片：值、状态、说明与原文证据。 */
export function FieldCard({ field, analysisMode }: { field: AnalysisField; analysisMode: AnalysisResult['analysis_mode'] }) {
  const state = fieldState(field, analysisMode)

  return (
    <article className="card field-card">
      <header className="field-head">
        <span>{field.label}</span>
        <Badge tone={state.tone}>{state.label}</Badge>
      </header>

      {field.value ? (
        <p className="field-value">{field.value}</p>
      ) : (
        <p className="field-value empty">原文中未找到可引用内容</p>
      )}

      {field.note && <p className="field-note">{field.note}</p>}

      <EvidenceList evidence={field.evidence} />
    </article>
  )
}
