import { useCallback, useEffect, useState } from 'react'

export const routeKeys = [
  'dashboard',
  'analyze',
  'matters',
  'verification',
  'tasks',
  'risks',
  'settings',
] as const

export type RouteKey = (typeof routeKeys)[number]

export type RouteParams = Record<string, string>

type RouteState = {
  route: RouteKey
  params: RouteParams
}

function splitHash(): { path: string; query: string } {
  const raw = window.location.hash.replace(/^#\/?/, '')
  const [path, query = ''] = raw.split('?')
  return { path, query }
}

/** 未知路由回退到总览时，把地址栏 hash 同步为 #/dashboard，避免页面与地址不一致。 */
function normalizeHash(): void {
  const { path, query } = splitHash()
  if ((routeKeys as readonly string[]).includes(path)) {
    return
  }
  const target = `#/dashboard${query ? `?${query}` : ''}`
  if (window.location.hash !== target) {
    // replaceState 不触发 hashchange，不会造成循环。
    window.history.replaceState(null, '', target)
  }
}

function parseHash(): RouteState {
  const { path, query } = splitHash()
  const route = (routeKeys as readonly string[]).includes(path)
    ? (path as RouteKey)
    : 'dashboard'
  const params: RouteParams = {}
  new URLSearchParams(query).forEach((value, key) => {
    params[key] = value
  })
  return { route, params }
}

/** 基于 URL hash 的轻量路由，支持查询参数，无需额外依赖。 */
export function useHashRoute() {
  const [state, setState] = useState<RouteState>(parseHash)

  useEffect(() => {
    const handleChange = () => {
      normalizeHash()
      setState(parseHash())
      window.scrollTo({ top: 0 })
    }
    window.addEventListener('hashchange', handleChange)
    normalizeHash()
    return () => window.removeEventListener('hashchange', handleChange)
  }, [])

  const navigate = useCallback((next: RouteKey, params?: RouteParams) => {
    const query = params ? new URLSearchParams(params).toString() : ''
    const target = `#/${next}${query ? `?${query}` : ''}`
    if (window.location.hash === target) {
      window.scrollTo({ top: 0 })
      return
    }
    window.location.hash = target
  }, [])

  return { route: state.route, params: state.params, navigate }
}
