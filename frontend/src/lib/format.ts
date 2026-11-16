/** 文件大小与日期的展示格式化。 */

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export function formatToday(): string {
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'full' }).format(new Date())
}

/** 统一的日期时间展示：去掉 ISO 的 T 与毫秒/时区后缀，空值显示占位符。 */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  return value.replace('T', ' ').slice(0, 19)
}
