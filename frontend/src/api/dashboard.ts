/** 总览统计接口客户端（真实数据，按正式 / 演示隔离）。 */

import { requestJson } from './client'
import type { DashboardSummary } from '../types'

export function fetchDashboardSummary(
  demo: boolean,
  signal?: AbortSignal,
): Promise<DashboardSummary> {
  const suffix = demo ? '?demo=true' : ''
  return requestJson<DashboardSummary>(`/api/dashboard/summary${suffix}`, { signal })
}
