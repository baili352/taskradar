/** 参赛演示数据接口客户端。 */

import { requestJson } from './client'
import type { DemoStatus } from '../types'

export function fetchDemoStatus(signal?: AbortSignal): Promise<DemoStatus> {
  return requestJson<DemoStatus>('/api/demo/status', { signal })
}

export function seedDemoData(signal?: AbortSignal): Promise<DemoStatus> {
  return requestJson<DemoStatus>('/api/demo/seed', { method: 'POST', signal })
}

export function clearDemoData(signal?: AbortSignal): Promise<DemoStatus> {
  return requestJson<DemoStatus>('/api/demo/clear', { method: 'DELETE', signal })
}
