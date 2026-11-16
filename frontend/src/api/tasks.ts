/** 任务接口客户端：任务来自后端 SQLite，不做本地伪造。 */

import { ApiRequestError, requestJson } from './client'
import type {
  TaskCreatePayload,
  TaskGenerationResult,
  TaskPriority,
  TaskRecord,
  TaskStatus,
  TaskUpdatePayload,
} from '../types'

export function taskErrorMessage(reason: unknown, fallback: string): string {
  return reason instanceof ApiRequestError ? reason.message : fallback
}

export type TaskQuery = {
  matterId?: number
  status?: TaskStatus
  priority?: TaskPriority
}

export function fetchTasks(query: TaskQuery = {}): Promise<TaskRecord[]> {
  const params = new URLSearchParams()
  if (query.matterId) params.set('matter_id', String(query.matterId))
  if (query.status) params.set('status', query.status)
  if (query.priority) params.set('priority', query.priority)
  const suffix = params.toString() ? `?${params.toString()}` : ''
  return requestJson<TaskRecord[]>(`/api/tasks${suffix}`)
}

export function fetchTask(taskId: number): Promise<TaskRecord> {
  return requestJson<TaskRecord>(`/api/tasks/${taskId}`)
}

export function generateTasksForMatter(matterId: number): Promise<TaskGenerationResult> {
  return requestJson<TaskGenerationResult>(`/api/matters/${matterId}/tasks`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
}

export function createTask(payload: TaskCreatePayload): Promise<TaskRecord> {
  return requestJson<TaskRecord>('/api/tasks', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateTask(taskId: number, payload: TaskUpdatePayload): Promise<TaskRecord> {
  return requestJson<TaskRecord>(`/api/tasks/${taskId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function deleteTask(taskId: number): Promise<void> {
  return requestJson<void>(`/api/tasks/${taskId}`, { method: 'DELETE' })
}
