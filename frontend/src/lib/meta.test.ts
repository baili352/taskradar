import { describe, expect, it } from 'vitest'

import {
  deadlineSourceMeta,
  materialRecordStatusMeta,
  matterStatusMeta,
  priorityMeta,
  riskLevelMeta,
  riskStatusMeta,
  riskTypeMeta,
} from './meta'

const KNOWN_TONES = new Set(['danger', 'warning', 'success', 'info', 'neutral'])

describe('事项与任务状态文案', () => {
  it('事项状态映射', () => {
    expect(matterStatusMeta.in_progress).toEqual({ label: '进行中', tone: 'info' })
    expect(matterStatusMeta.pending).toEqual({ label: '待开始', tone: 'warning' })
    expect(matterStatusMeta.done).toEqual({ label: '已完成', tone: 'success' })
  })

  it('任务优先级映射', () => {
    expect(priorityMeta.high.label).toBe('高优先级')
    expect(priorityMeta.medium.tone).toBe('warning')
    expect(priorityMeta.low.label).toBe('低优先级')
  })
})

describe('材料与风险状态文案', () => {
  it('材料核验六种状态都有文案与色调', () => {
    const statuses = [
      'missing',
      'pending',
      'qualified',
      'incomplete',
      'conflict',
      'uncertain',
    ] as const
    for (const status of statuses) {
      expect(materialRecordStatusMeta[status].label.length).toBeGreaterThan(0)
      expect(KNOWN_TONES.has(materialRecordStatusMeta[status].tone)).toBe(true)
    }
    expect(materialRecordStatusMeta.missing).toEqual({ label: '未提供', tone: 'danger' })
    expect(materialRecordStatusMeta.qualified).toEqual({ label: '已确认', tone: 'success' })
  })

  it('风险等级、状态与类型文案完整', () => {
    expect(riskLevelMeta.high).toEqual({ label: '高风险', tone: 'danger' })
    expect(riskStatusMeta.resolved).toEqual({ label: '已解决', tone: 'success' })
    for (const meta of Object.values(riskTypeMeta)) {
      expect(meta.label.length).toBeGreaterThan(0)
      expect(meta.description.length).toBeGreaterThan(0)
    }
  })

  it('截止日期来源映射包含常见取值', () => {
    expect(deadlineSourceMeta.document).toBe('原文明确日期')
    expect(deadlineSourceMeta.manual).toBe('用户手动设置')
    expect(deadlineSourceMeta.none).toBe('未设置')
  })
})

describe('异常输入', () => {
  it('未知状态键返回 undefined 而不是抛错', () => {
    const looseMatterStatus = matterStatusMeta as unknown as Record<string, unknown>
    expect(looseMatterStatus.unknown).toBeUndefined()

    const looseDeadlineSource = deadlineSourceMeta as Record<string, string | undefined>
    expect(looseDeadlineSource['']).toBeUndefined()
    expect(() => looseDeadlineSource['no_such_source']).not.toThrow()
  })

  it('所有色调取值都在已知集合内', () => {
    const groups = [
      matterStatusMeta,
      materialRecordStatusMeta,
      priorityMeta,
      riskLevelMeta,
      riskStatusMeta,
    ]
    for (const group of groups) {
      for (const meta of Object.values(group)) {
        expect(KNOWN_TONES.has(meta.tone)).toBe(true)
      }
    }
  })
})
