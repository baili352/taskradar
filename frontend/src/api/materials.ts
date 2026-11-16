/** 材料清单与核验接口客户端。 */

import { ApiRequestError, requestForm, requestJson } from './client'
import type {
  MaterialConfirmPayload,
  MaterialCreatePayload,
  MaterialGenerationResult,
  MaterialProgress,
  MaterialRecord,
  MaterialRecordStatus,
  MaterialUpdatePayload,
} from '../types'

const BASE = '/api'

export function fetchMaterials(params: {
  matterId?: number
  status?: MaterialRecordStatus
} = {}): Promise<MaterialRecord[]> {
  const query = new URLSearchParams()
  if (params.matterId) query.set('matter_id', String(params.matterId))
  if (params.status) query.set('status', params.status)
  const suffix = query.toString() ? `?${query.toString()}` : ''
  return requestJson<MaterialRecord[]>(`${BASE}/materials${suffix}`)
}

export function fetchMatterMaterials(matterId: number): Promise<MaterialRecord[]> {
  return requestJson<MaterialRecord[]>(`${BASE}/matters/${matterId}/materials`)
}

export function fetchMaterial(materialId: number): Promise<MaterialRecord> {
  return requestJson<MaterialRecord>(`${BASE}/materials/${materialId}`)
}

export function generateMaterials(matterId: number): Promise<MaterialGenerationResult> {
  return requestJson<MaterialGenerationResult>(
    `${BASE}/matters/${matterId}/materials/generate`,
    { method: 'POST' },
  )
}

export function createMaterial(
  matterId: number,
  payload: MaterialCreatePayload,
): Promise<MaterialRecord> {
  return requestJson<MaterialRecord>(`${BASE}/matters/${matterId}/materials`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateMaterial(
  materialId: number,
  payload: MaterialUpdatePayload,
): Promise<MaterialRecord> {
  return requestJson<MaterialRecord>(`${BASE}/materials/${materialId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function deleteMaterial(materialId: number): Promise<void> {
  return requestJson<void>(`${BASE}/materials/${materialId}`, { method: 'DELETE' })
}

export function uploadMaterialFile(
  materialId: number,
  file: File,
): Promise<MaterialRecord> {
  const formData = new FormData()
  formData.append('file', file)
  return requestForm<MaterialRecord>(`${BASE}/materials/${materialId}/file`, formData)
}

export function verifyMaterial(materialId: number): Promise<MaterialRecord> {
  return requestJson<MaterialRecord>(`${BASE}/materials/${materialId}/verify`, {
    method: 'POST',
  })
}

export function confirmMaterial(
  materialId: number,
  payload: MaterialConfirmPayload,
): Promise<MaterialRecord> {
  return requestJson<MaterialRecord>(`${BASE}/materials/${materialId}/confirm`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function fetchMaterialProgress(matterId: number): Promise<MaterialProgress> {
  return requestJson<MaterialProgress>(
    `${BASE}/matters/${matterId}/materials/progress`,
  )
}

export function materialErrorMessage(reason: unknown, fallback: string): string {
  return reason instanceof ApiRequestError ? reason.message : fallback
}
