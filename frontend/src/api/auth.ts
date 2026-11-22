/** 登录注册接口客户端。 */

import { requestJson } from './client'

export type AuthUser = {
  id: number
  username: string
}

export type AuthState = {
  enabled: boolean
  authenticated: boolean
  user: AuthUser | null
}

export function fetchAuthState(): Promise<AuthState> {
  return requestJson<AuthState>('/api/auth/me')
}

export function login(username: string, password: string): Promise<AuthState> {
  return requestJson<AuthState>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
}

export function register(
  username: string,
  password: string,
  inviteCode: string,
): Promise<AuthState> {
  return requestJson<AuthState>('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({ username, password, invite_code: inviteCode }),
  })
}

export function logout(): Promise<AuthState> {
  return requestJson<AuthState>('/api/auth/logout', { method: 'POST' })
}
