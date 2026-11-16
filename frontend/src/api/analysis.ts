/** 智能分析接口客户端：使用 XMLHttpRequest 以获得真实上传进度。 */

import type { AIConnectionTestResult, AnalysisCapabilities, AnalysisResult } from '../types'

export class AnalysisRequestError extends Error {
  code: string

  constructor(message: string, code = 'request_failed') {
    super(message)
    this.name = 'AnalysisRequestError'
    this.code = code
  }
}

type AnalyzeOptions = {
  onProgress?: (percent: number) => void
  onUploaded?: () => void
}

function readError(payload: unknown, status: number): AnalysisRequestError {
  if (payload && typeof payload === 'object') {
    const detail = (payload as { detail?: unknown }).detail
    if (detail && typeof detail === 'object') {
      const { code, message } = detail as { code?: unknown; message?: unknown }
      if (typeof message === 'string' && message.trim()) {
        return new AnalysisRequestError(message, typeof code === 'string' ? code : 'request_failed')
      }
    }
    if (typeof detail === 'string' && detail.trim()) {
      return new AnalysisRequestError(detail)
    }
  }

  if (status === 413) {
    return new AnalysisRequestError('文件超过大小上限，请压缩或拆分后再上传。', 'file_too_large')
  }
  if (status === 415) {
    return new AnalysisRequestError('不支持的文件格式，请上传 PDF / DOCX / TXT / PNG / JPG / JPEG 文件。', 'unsupported_format')
  }
  return new AnalysisRequestError(`分析请求失败（HTTP ${status}），请稍后重试。`)
}

export function analyzeDocument(file: File, options: AnalyzeOptions = {}): Promise<AnalysisResult> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/analysis/analyze')
    xhr.responseType = 'json'
    xhr.timeout = 600000

    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable || event.total === 0) return
      options.onProgress?.(Math.min(100, Math.round((event.loaded / event.total) * 100)))
    }

    xhr.upload.onload = () => {
      options.onProgress?.(100)
      options.onUploaded?.()
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(xhr.response as AnalysisResult)
        return
      }
      reject(readError(xhr.response, xhr.status))
    }

    xhr.onerror = () => {
      reject(
        new AnalysisRequestError(
          '无法连接后端服务，请确认后端已在 8000 端口启动。',
          'network_error',
        ),
      )
    }

    xhr.ontimeout = () => {
      reject(new AnalysisRequestError('分析超时；OCR 与大模型可能需要较长时间，请重试或拆分较小的文件。', 'timeout'))
    }

    const form = new FormData()
    form.append('file', file, file.name)
    xhr.send(form)
  })
}

export async function fetchAnalysisCapabilities(): Promise<AnalysisCapabilities> {
  const response = await fetch('/api/analysis/capabilities')
  if (!response.ok) {
    throw new AnalysisRequestError('无法读取分析能力状态，请确认后端服务是否正常。')
  }
  return (await response.json()) as AnalysisCapabilities
}

export async function testAIConnection(): Promise<AIConnectionTestResult> {
  let response: Response
  try {
    response = await fetch('/api/analysis/ai/test', { method: 'POST' })
  } catch {
    throw new AnalysisRequestError('无法连接后端服务，请确认后端是否已启动。', 'network_error')
  }
  const payload: unknown = await response.json().catch(() => null)
  if (!response.ok) throw readError(payload, response.status)
  return payload as AIConnectionTestResult
}
