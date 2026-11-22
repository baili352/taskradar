import { useState, type FormEvent } from 'react'
import { ShieldCheck } from 'lucide-react'
import { login, register, type AuthState } from '../api/auth'
import { ApiRequestError } from '../api/client'

type LoginPageProps = {
  onAuthenticated: (state: AuthState) => void
}

type Mode = 'login' | 'register'

export function LoginPage({ onAuthenticated }: LoginPageProps) {
  const [mode, setMode] = useState<Mode>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [inviteCode, setInviteCode] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const switchMode = (next: Mode) => {
    setMode(next)
    setError('')
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError('')
    if (mode === 'register' && password.length < 8) {
      setError('密码至少 8 位')
      return
    }
    setSubmitting(true)
    try {
      const state =
        mode === 'login'
          ? await login(username.trim(), password)
          : await register(username.trim(), password, inviteCode.trim())
      onAuthenticated(state)
    } catch (reason) {
      setError(
        reason instanceof ApiRequestError ? reason.message : '请求失败，请稍后重试',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="login-shell">
      <div className="login-card">
        <div className="login-brand">
          <span className="login-logo">
            <ShieldCheck size={22} />
          </span>
          <div>
            <strong>办事雷达 TaskRadar AI</strong>
            <small>事项拆解 · 材料核验 · 风险提醒</small>
          </div>
        </div>

        <div className="login-tabs" role="tablist" aria-label="登录或注册">
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'login'}
            className={mode === 'login' ? 'active' : ''}
            onClick={() => switchMode('login')}
          >
            登录
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'register'}
            className={mode === 'register' ? 'active' : ''}
            onClick={() => switchMode('register')}
          >
            注册
          </button>
        </div>

        <form className="login-form" onSubmit={handleSubmit}>
          <label>
            <span>用户名</span>
            <input
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
              minLength={2}
              maxLength={32}
              required
            />
          </label>
          <label>
            <span>密码</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              minLength={mode === 'register' ? 8 : 1}
              maxLength={128}
              required
            />
          </label>
          {mode === 'register' && (
            <label>
              <span>邀请码</span>
              <input
                value={inviteCode}
                onChange={(event) => setInviteCode(event.target.value)}
                placeholder="向管理员获取"
                required
              />
            </label>
          )}

          {error && <p className="login-error">{error}</p>}

          <button type="submit" className="btn btn-primary login-submit" disabled={submitting}>
            {submitting ? '处理中…' : mode === 'login' ? '登录' : '注册并登录'}
          </button>
        </form>

        <p className="login-hint">
          {mode === 'login'
            ? '没有账号？切换到「注册」，需要管理员提供的邀请码。'
            : '注册后即登录；演示数据对所有登录用户可见。'}
        </p>
      </div>
    </div>
  )
}
