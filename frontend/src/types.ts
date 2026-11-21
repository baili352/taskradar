/** 全局共享类型定义。 */

export type BadgeTone = 'neutral' | 'info' | 'success' | 'warning' | 'danger' | 'demo'

export type MatterStatus = 'in_progress' | 'pending' | 'done'

export type TaskPriority = 'high' | 'medium' | 'low'

export type HealthData = {
  status: string
  app: string
  version: string
  environment: string
  database: string
  time: string
}

/* ---------------- 智能分析（第三阶段，对接真实后端） ---------------- */

export type Evidence = {
  text: string
  location: string
  page?: number | null
  paragraph?: number | null
}

export type AnalysisFieldStatus = 'found' | 'pending'

export type AnalysisField = {
  key: string
  label: string
  value: string | null
  status: AnalysisFieldStatus
  evidence: Evidence[]
  note: string | null
}

export type AnalysisMaterial = {
  name: string
  status: 'found'
  evidence: Evidence
}

export type AnalysisProcessStep = {
  index: number
  text: string
  evidence: Evidence
}

export type AnalysisNote = {
  text: string
  evidence: Evidence
}

export type AnalysisDocumentInfo = {
  filename: string
  extension: string
  size: number
  char_count: number
  page_count: number | null
  paragraph_count: number | null
  ocr_used: boolean
  ocr_pages: number[]
}

export type AnalysisResult = {
  document: AnalysisDocumentInfo
  fields: AnalysisField[]
  materials: AnalysisMaterial[]
  process: AnalysisProcessStep[]
  notes: AnalysisNote[]
  warnings: string[]
  analysis_mode: 'rule_based' | 'ai_assisted' | 'rule_fallback'
  ai_configured: boolean
  ai_message: string
  elapsed_ms: number
}

export type AnalysisCapabilities = {
  analysis_mode: 'rule_based' | 'ai_assisted' | 'rule_fallback'
  ai_configured: boolean
  ai_provider: string
  ai_model: string
  ai_key_configured: boolean
  ai_message: string
  ocr_enabled: boolean
  ocr_available: boolean
  ocr_message: string
  supported_extensions: string[]
  max_upload_mb: number
}

export type AIConnectionTestResult = {
  success: boolean
  message: string
  model: string
  elapsed_ms: number
}

/* ---------------- 事项持久化（第四阶段，SQLite 真实数据） ---------------- */

export type MatterRecord = {
  id: number
  name: string
  matter_type: string
  qualification: string
  registration_start: string | null
  deadline: string | null
  deadline_source: TaskDeadlineSource
  materials: AnalysisMaterial[]
  process: AnalysisProcessStep[]
  notes: AnalysisNote[]
  fields: AnalysisField[]
  source_filename: string
  status: MatterStatus
  analysis_mode: string
  is_demo: boolean
  created_at: string
  updated_at: string
}

export type MatterCreatePayload = {
  name: string
  matter_type?: string
  qualification?: string
  registration_start?: string | null
  deadline?: string | null
  deadline_source?: TaskDeadlineSource
  materials?: AnalysisMaterial[]
  process?: AnalysisProcessStep[]
  notes?: AnalysisNote[]
  fields?: AnalysisField[]
  source_filename?: string
  status?: MatterStatus
  analysis_mode?: string
}

export type MatterUpdatePayload = Partial<MatterCreatePayload>

/* ---------------- 任务（第四阶段第二步，对接真实后端） ---------------- */

export type TaskStatus = 'pending' | 'in_progress' | 'done'

export type TaskDeadlineSource = 'document' | 'suggested' | 'manual' | 'none'

export type TaskOrigin = 'generated' | 'manual'

export type TaskRecord = {
  id: number
  matter_id: number
  title: string
  description: string
  deadline: string | null
  deadline_source: TaskDeadlineSource
  priority: TaskPriority
  status: TaskStatus
  origin: TaskOrigin
  source_evidence: Evidence | null
  is_demo: boolean
  created_at: string
  updated_at: string
}

export type TaskCreatePayload = {
  matter_id: number
  title: string
  description?: string
  deadline?: string | null
  deadline_source?: TaskDeadlineSource
  priority?: TaskPriority
  status?: TaskStatus
}

export type TaskUpdatePayload = {
  title?: string
  description?: string
  deadline?: string | null
  deadline_source?: TaskDeadlineSource
  priority?: TaskPriority
  status?: TaskStatus
}

export type TaskGenerationResult = {
  matter_id: number
  created: number
  skipped: number
  total_process_steps: number
  message: string
  tasks: TaskRecord[]
  suggestion: {
    deadline: string | null
    note: string
    task_ids: number[]
  } | null
}

/* ---------------- 材料清单与核验（第四阶段第三步，对接真实后端） ---------------- */

export type MaterialRecordStatus =
  | 'missing'
  | 'pending'
  | 'qualified'
  | 'incomplete'
  | 'conflict'
  | 'uncertain'

export type MaterialVerificationResult =
  | 'qualified'
  | 'incomplete'
  | 'conflict'
  | 'uncertain'

export type MaterialCheckStatus = 'pass' | 'warn' | 'unknown'

export type MaterialVerificationCheck = {
  key: string
  label: string
  status: MaterialCheckStatus
  message: string
  excerpt: string | null
  location: string | null
}

export type MaterialVerification = {
  result: MaterialVerificationResult
  source: 'rule' | 'manual'
  verified_at: string
  summary: string
  checks: MaterialVerificationCheck[]
  reasons: string[]
  reviewer_note: string | null
}

export type MaterialEvent = {
  id: number
  action: string
  detail: string
  created_at: string
}

export type MaterialRecord = {
  id: number
  matter_id: number
  matter_name: string
  name: string
  description: string
  status: MaterialRecordStatus
  file_path: string | null
  original_filename: string | null
  file_size: number | null
  file_type: string | null
  verification: MaterialVerification | null
  source_evidence: Evidence | null
  origin: 'generated' | 'manual'
  is_demo: boolean
  created_at: string
  updated_at: string
  events: MaterialEvent[]
}

export type MaterialCreatePayload = {
  name: string
  description?: string
  source_evidence?: Evidence | null
}

export type MaterialUpdatePayload = {
  name?: string
  description?: string
}

export type MaterialConfirmPayload = {
  status: MaterialVerificationResult
  note?: string
  evidence_text?: string | null
}

export type MaterialGenerationResult = {
  matter_id: number
  created: number
  skipped: number
  total_source_materials: number
  message: string
  materials: MaterialRecord[]
}

export type MaterialProgress = {
  matter_id: number
  total: number
  missing: number
  provided: number
  pending: number
  qualified: number
  incomplete: number
  conflict: number
  uncertain: number
  prepared_percent: number
  verified_percent: number
}

/* ---------------- 风险提醒（第四阶段第四步，对接真实后端） ---------------- */

export type RiskType =
  | 'overdue'
  | 'due_soon'
  | 'backlog'
  | 'material_missing'
  | 'material_pending'
  | 'material_incomplete'
  | 'material_conflict'
  | 'material_uncertain'
  | 'date_unverified'

export type RiskLevel = 'high' | 'medium' | 'low'

export type RiskStatus = 'active' | 'read' | 'resolved'

export type RiskStatusFilter = 'active' | 'read' | 'resolved' | 'unresolved' | 'all'

export type MatterDeadlineState =
  | 'none'
  | 'unverified'
  | 'suggested'
  | 'overdue'
  | 'today'
  | 'due_soon'
  | 'normal'
  | 'completed'

export type RiskTaskRef = {
  id: number
  title: string
  status: TaskStatus
  deadline: string | null
  deadline_source: TaskDeadlineSource | null
  days_left: number | null
}

export type RiskMaterialEvidence = {
  name: string
  description: string
  status: MaterialRecordStatus
  original_filename: string | null
  file_type: string | null
  file_size: number | null
  requirement_evidence: Evidence | null
  verification: MaterialVerification | null
}

export type RiskEvidence = {
  rule: string
  data_sources: string[]
  timezone: string | null
  today: string | null
  deadline_raw: string | null
  deadline_normalized: string | null
  deadline_source: string | null
  days_left: number | null
  matter_name: string | null
  task: RiskTaskRef | null
  unfinished_tasks: RiskTaskRef[]
  material: RiskMaterialEvidence | null
  note: string | null
}

export type RiskRecord = {
  id: number
  fingerprint: string
  risk_type: RiskType
  risk_level: RiskLevel
  title: string
  description: string
  matter_id: number
  matter_name: string
  task_id: number | null
  task_title: string | null
  material_id: number | null
  material_name: string | null
  evidence: RiskEvidence | null
  suggestion: string
  status: RiskStatus
  is_demo: boolean
  first_seen_at: string
  last_seen_at: string
  read_at: string | null
  resolved_at: string | null
}

export type RiskSummary = {
  generated_at: string
  timezone: string
  today: string
  total_unresolved: number
  total_risks: number
  active: number
  read: number
  resolved: number
  high: number
  medium: number
  low: number
  by_type: Partial<Record<RiskType, number>>
  overdue_tasks: number
  due_soon_3d_tasks: number
  due_soon_7d_tasks: number
  pending_materials: number
  conflict_materials: number
  missing_materials: number
  uncertain_materials: number
  unfinished_tasks: number
  matters_with_risks: number
}

export type RiskListResponse = {
  total: number
  items: RiskRecord[]
}

export type MatterRiskSummary = {
  matter_id: number
  matter_name: string
  matter_status: MatterStatus
  deadline: string | null
  deadline_source: TaskDeadlineSource
  deadline_state: MatterDeadlineState
  deadline_days_left: number | null
  unfinished_tasks: number
  material_total: number
  material_missing: number
  material_pending: number
  material_conflict: number
  risk_total: number
  level: RiskLevel
  headline: string
}

export type MatterRisksResponse = {
  summary: MatterRiskSummary
  risks: RiskRecord[]
}

export type RiskRefreshResult = {
  generated_at: string
  created: number
  updated: number
  revived: number
  resolved: number
  summary: RiskSummary
}

/* ---------------- 总览与演示数据（第五阶段第三步） ---------------- */

export type DashboardScope = 'real' | 'demo'

export type DashboardSummary = {
  scope: DashboardScope
  generated_at: string
  timezone: string
  today: string
  matters: {
    total: number
    pending: number
    in_progress: number
    done: number
  }
  tasks: {
    total: number
    unfinished: number
    done: number
    overdue: number
    due_soon_3d: number
    due_soon_7d: number
  }
  materials: {
    total: number
    missing: number
    pending: number
    qualified: number
    incomplete: number
    conflict: number
    uncertain: number
    provided: number
    prepared_percent: number
    verified_percent: number
  }
  risks: {
    unresolved: number
    high: number
    medium: number
    low: number
  }
  recent_matters: {
    id: number
    name: string
    matter_type: string
    status: MatterStatus
    deadline: string | null
    deadline_source: TaskDeadlineSource
    updated_at: string
  }[]
  due_soon_tasks: {
    id: number
    title: string
    matter_id: number
    matter_name: string
    deadline: string | null
    deadline_source: TaskDeadlineSource
    priority: TaskPriority
    status: TaskStatus
    days_left: number | null
    overdue: boolean
  }[]
}

export type DemoStatus = {
  available: boolean
  seeded: boolean
  matters: number
  tasks: number
  materials: number
  risks: number
  real_matters: number
  seeded_at: string | null
  refreshed: boolean
  message: string
}

