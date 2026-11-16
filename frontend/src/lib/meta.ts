import type {
  BadgeTone,
  MaterialRecordStatus,
  MatterStatus,
  RiskLevel,
  RiskStatus,
  RiskType,
  TaskPriority,
} from '../types'

export const matterStatusMeta: Record<MatterStatus, { label: string; tone: BadgeTone }> = {
  in_progress: { label: '进行中', tone: 'info' },
  pending: { label: '待开始', tone: 'warning' },
  done: { label: '已完成', tone: 'success' },
}

export const materialRecordStatusMeta: Record<
  MaterialRecordStatus,
  { label: string; tone: BadgeTone }
> = {
  missing: { label: '未提供', tone: 'danger' },
  pending: { label: '待核验', tone: 'warning' },
  qualified: { label: '已确认', tone: 'success' },
  incomplete: { label: '信息不完整', tone: 'warning' },
  conflict: { label: '存在冲突', tone: 'danger' },
  uncertain: { label: '无法判断', tone: 'neutral' },
}

export const priorityMeta: Record<TaskPriority, { label: string; tone: BadgeTone }> = {
  high: { label: '高优先级', tone: 'danger' },
  medium: { label: '中优先级', tone: 'warning' },
  low: { label: '低优先级', tone: 'neutral' },
}

/* ---------------- 风险提醒元数据 ---------------- */

export const riskLevelMeta: Record<RiskLevel, { label: string; tone: BadgeTone }> = {
  high: { label: '高风险', tone: 'danger' },
  medium: { label: '中风险', tone: 'warning' },
  low: { label: '低风险', tone: 'neutral' },
}

export const riskStatusMeta: Record<RiskStatus, { label: string; tone: BadgeTone }> = {
  active: { label: '待处理', tone: 'warning' },
  read: { label: '已读', tone: 'info' },
  resolved: { label: '已解决', tone: 'success' },
}

export const riskTypeMeta: Record<RiskType, { label: string; description: string }> = {
  overdue: { label: '任务逾期', description: '任务有明确截止日期且已超期，任务尚未完成' },
  due_soon: { label: '即将截止', description: '任务将在 7 天内截止，3 天内为中高风险' },
  backlog: { label: '任务积压', description: '事项下存在多个未完成任务' },
  material_missing: { label: '材料缺失', description: '必需材料尚未提供' },
  material_pending: { label: '材料待核验', description: '材料已提供但尚未核验' },
  material_incomplete: { label: '材料不完整', description: '材料信息不完整，需要人工确认' },
  material_conflict: { label: '材料冲突', description: '材料存在冲突信息' },
  material_uncertain: { label: '材料无法判断', description: '规则无法判断，需要人工检查' },
  date_unverified: { label: '日期待核实', description: '截止日期无法解析，暂不参与到期判断' },
}

export const deadlineSourceMeta: Record<string, string> = {
  document: '原文明确日期',
  manual: '用户手动设置',
  suggested: '系统建议日期（未应用）',
  none: '未设置',
}
