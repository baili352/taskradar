/** 事项持久化接口客户端：全部请求真实写入后端 SQLite。 */

import { ApiRequestError, requestJson } from './client'
import type { MatterCreatePayload, MatterRecord, MatterUpdatePayload } from '../types'

/**
 * 兼容既有调用方的错误类型：与通用 ApiRequestError 是同一个类，
 * 因此 MattersPage 中的 instanceof 判断仍然有效。
 */
export { ApiRequestError as MatterRequestError }

export function createMatter(payload: MatterCreatePayload): Promise<MatterRecord> {
  return requestJson<MatterRecord>('/api/matters', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function fetchMatters(): Promise<MatterRecord[]> {
  return requestJson<MatterRecord[]>('/api/matters')
}

export function fetchMatter(matterId: number): Promise<MatterRecord> {
  return requestJson<MatterRecord>(`/api/matters/${matterId}`)
}

export function updateMatter(
  matterId: number,
  payload: MatterUpdatePayload,
): Promise<MatterRecord> {
  return requestJson<MatterRecord>(`/api/matters/${matterId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}
