import { describe, expect, it } from 'vitest'

import { formatDateTime, formatFileSize, formatToday } from './format'

describe('formatFileSize', () => {
  it('小于 1KB 时按字节展示', () => {
    expect(formatFileSize(0)).toBe('0 B')
    expect(formatFileSize(512)).toBe('512 B')
    expect(formatFileSize(1023)).toBe('1023 B')
  })

  it('KB 与 MB 的边界按四舍五入与一位小数展示', () => {
    expect(formatFileSize(1024)).toBe('1 KB')
    expect(formatFileSize(1536)).toBe('2 KB')
    expect(formatFileSize(1024 * 1024 - 1)).toBe('1024 KB')
    expect(formatFileSize(1024 * 1024)).toBe('1.0 MB')
    expect(formatFileSize(1.5 * 1024 * 1024)).toBe('1.5 MB')
  })

  it('异常输入不抛错，仍返回字符串', () => {
    expect(() => formatFileSize(-1)).not.toThrow()
    expect(typeof formatFileSize(-1)).toBe('string')
    expect(() => formatFileSize(Number.NaN)).not.toThrow()
    expect(typeof formatFileSize(Number.NaN)).toBe('string')
  })
})

describe('formatDateTime', () => {
  it('空值统一显示占位符', () => {
    expect(formatDateTime(null)).toBe('—')
    expect(formatDateTime(undefined)).toBe('—')
    expect(formatDateTime('')).toBe('—')
  })

  it('截断 ISO 的 T、毫秒与时区，只保留到秒', () => {
    expect(formatDateTime('2026-11-17T09:30:05')).toBe('2026-11-17 09:30:05')
    expect(formatDateTime('2026-11-17T09:30:05.123456')).toBe('2026-11-17 09:30:05')
    expect(formatDateTime('2026-11-17T01:30:05Z')).toBe('2026-11-17 01:30:05')
  })

  it('非 ISO 输入原样返回，不抛错', () => {
    expect(formatDateTime('2026-11-17')).toBe('2026-11-17')
    expect(formatDateTime('不是日期')).toBe('不是日期')
  })
})

describe('formatToday', () => {
  it('返回非空的完整中文日期', () => {
    const today = formatToday()
    expect(today.length).toBeGreaterThan(0)
    expect(today).toContain('年')
  })
})
