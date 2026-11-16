/** 风险提醒接口客户端。 */

import { ApiRequestError, requestJson } from './client'
import type {
  MatterRisksResponse,
  RiskLevel,
  RiskListResponse,
  RiskRecord,
  RiskRefreshResult,
  RiskStatusFilter,
  RiskSummary,
  RiskType,
} from '../types'

const BASE = '/api'

export type RiskQuery = {
  riskType?: RiskType
  level?: RiskLevel
  status?: RiskStatusFilter
  matterId?: number
  limit?: number
  offset?: number
}

export function fetchRiskSummary(signal?: AbortSignal): Promise<RiskSummary> {
  return requestJson<RiskSummary>(`${BASE}/risks/summary`, { signal })
}

export function fetchRisks(
  query: RiskQuery = {},
  signal?: AbortSignal,
): Promise<RiskListResponse> {
  const params = new URLSearchParams()
  if (query.riskType) params.set('risk_type', query.riskType)
  if (query.level) params.set('level', query.level)
  if (query.status) params.set('status', query.status)
  if (query.matterId) params.set('matter_id', String(query.matterId))
  if (query.limit) params.set('limit', String(query.limit))
  if (query.offset) params.set('offset', String(query.offset))
  const suffix = params.toString() ? `?${params.toString()}` : ''
  return requestJson<RiskListResponse>(`${BASE}/risks${suffix}`, { signal })
}

export function fetchRisk(riskId: number, signal?: AbortSignal): Promise<RiskRecord> {
  return requestJson<RiskRecord>(`${BASE}/risks/${riskId}`, { signal })
}

export function markRiskRead(riskId: number, signal?: AbortSignal): Promise<RiskRecord> {
  return requestJson<RiskRecord>(`${BASE}/risks/${riskId}/read`, {
    method: 'PATCH',
    signal,
  })
}

export function refreshRisks(signal?: AbortSignal): Promise<RiskRefreshResult> {
  return requestJson<RiskRefreshResult>(`${BASE}/risks/refresh`, {
    method: 'POST',
    signal,
  })
}

export function fetchMatterRisks(
  matterId: number,
  signal?: AbortSignal,
): Promise<MatterRisksResponse> {
  return requestJson<MatterRisksResponse>(`${BASE}/matters/${matterId}/risks`, { signal })
}

export function riskErrorMessage(reason: unknown, fallback: string): string {
  return reason instanceof ApiRequestError ? reason.message : fallback
}
