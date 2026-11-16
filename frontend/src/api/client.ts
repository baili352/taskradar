/** 通用接口客户端：统一处理网络错误与后端错误体。 */

export class ApiRequestError extends Error {
  code: string

  constructor(message: string, code = 'request_failed') {
    super(message)
    this.name = 'ApiRequestError'
    this.code = code
  }
}

function describeDetail(detail: unknown): { message: string; code: string } | null {
  if (typeof detail === 'string' && detail.trim()) {
    return { message: detail, code: 'request_failed' }
  }
  if (Array.isArray(detail) && detail.length > 0) {
    // FastAPI 参数校验错误：提取第一条可读信息，不隐藏真实原因。
    const first = detail[0] as { loc?: unknown[]; msg?: string }
    const field = Array.isArray(first?.loc) ? first.loc.slice(1).join('.') : ''
    const message = first?.msg ?? '请求参数不合法'
    return {
      message: field ? `字段「${field}」校验失败：${message}` : message,
      code: 'validation_error',
    }
  }
  if (detail && typeof detail === 'object') {
    const { code, message } = detail as { code?: unknown; message?: unknown }
    if (typeof message === 'string' && message.trim()) {
      return {
        message,
        code: typeof code === 'string' ? code : 'request_failed',
      }
    }
  }
  return null
}

async function readError(response: Response): Promise<ApiRequestError> {
  let payload: unknown = null
  try {
    payload = await response.json()
  } catch {
    payload = null
  }

  if (payload && typeof payload === 'object') {
    const parsed = describeDetail((payload as { detail?: unknown }).detail)
    if (parsed) return new ApiRequestError(parsed.message, parsed.code)
  }

  if (response.status === 404) {
    return new ApiRequestError('请求的数据不存在或已被删除。', 'not_found')
  }
  if (response.status === 422) {
    return new ApiRequestError('提交的数据格式不合法，请检查后重试。', 'validation_error')
  }
  return new ApiRequestError(
    `服务器返回错误（HTTP ${response.status}），请稍后重试。`,
    'server_error',
  )
}

const DEFAULT_TIMEOUT_MS = 30_000
const FORM_TIMEOUT_MS = 60_000

export function isRequestCancelled(reason: unknown): boolean {
  return reason instanceof ApiRequestError && reason.code === 'request_cancelled'
}

async function fetchWithTimeout(
  path: string,
  init: RequestInit | undefined,
  timeoutMs: number,
): Promise<Response> {
  const controller = new AbortController()
  const callerSignal = init?.signal
  let timedOut = false
  const abortFromCaller = () => controller.abort()
  if (callerSignal?.aborted) controller.abort()
  callerSignal?.addEventListener('abort', abortFromCaller, { once: true })
  const timer = globalThis.setTimeout(() => {
    timedOut = true
    controller.abort()
  }, timeoutMs)

  try {
    return await fetch(path, { ...init, signal: controller.signal })
  } catch (reason) {
    if (timedOut) {
      throw new ApiRequestError('请求超时，请检查网络连接或稍后重试。', 'request_timeout')
    }
    if (
      callerSignal?.aborted ||
      (reason instanceof Error && reason.name === 'AbortError')
    ) {
      throw new ApiRequestError('请求已取消。', 'request_cancelled')
    }
    throw new ApiRequestError(
      '无法连接后端服务，请确认后端已在 8000 端口启动。',
      'network_error',
    )
  } finally {
    globalThis.clearTimeout(timer)
    callerSignal?.removeEventListener('abort', abortFromCaller)
  }
}

export async function requestJson<T>(
  path: string,
  init?: RequestInit,
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  const response = await fetchWithTimeout(
    path,
    {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(init?.headers ?? {}),
      },
    },
    timeoutMs,
  )

  if (!response.ok) {
    throw await readError(response)
  }
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

/** 上传文件：不手动设置 Content-Type，交给浏览器生成 multipart boundary。 */
export async function requestForm<T>(
  path: string,
  formData: FormData,
  init?: RequestInit,
  timeoutMs = FORM_TIMEOUT_MS,
): Promise<T> {
  const response = await fetchWithTimeout(
    path,
    { ...init, method: init?.method ?? 'POST', body: formData },
    timeoutMs,
  )

  if (!response.ok) {
    throw await readError(response)
  }
  return (await response.json()) as T
}
