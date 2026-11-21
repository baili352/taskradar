/** 参赛演示数据接口客户端。 */

import { requestJson } from './client'
import type { DemoStatus } from '../types'

export function fetchDemoStatus(signal?: AbortSignal): Promise<DemoStatus> {
  return requestJson<DemoStatus>('/api/demo/status', { signal })
}

export function seedDemoData(signal?: AbortSignal): Promise<DemoStatus> {
  return requestJson<DemoStatus>('/api/demo/seed', { method: 'POST', signal })
}

/** 清空已有演示数据并按当天重新计算日期后再写入。 */
export function refreshDemoData(signal?: AbortSignal): Promise<DemoStatus> {
  return requestJson<DemoStatus>('/api/demo/seed?refresh=true', {
    method: 'POST',
    signal,
  })
}

export function clearDemoData(signal?: AbortSignal): Promise<DemoStatus> {
  return requestJson<DemoStatus>('/api/demo/clear', { method: 'DELETE', signal })
}
