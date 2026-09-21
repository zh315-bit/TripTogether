import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError } from '../api/client'
import type { RegisterRequest } from '../types/auth'

type FieldErrors = Partial<Record<keyof RegisterRequest, string>>
type Props = {
  mode: 'login' | 'register'
  onSubmit: (values: RegisterRequest, signal: AbortSignal) => Promise<void>
}

export function AuthForm({ mode, onSubmit }: Props) {
  const registering = mode === 'register'
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [pending, setPending] = useState(false)
  const [errors, setErrors] = useState<FieldErrors>({})
  const [message, setMessage] = useState('')
  const active = useRef<AbortController | null>(null)
  const errorSummary = useRef<HTMLDivElement>(null)

  useEffect(() => () => active.current?.abort(), [])
  useEffect(() => { if (message) errorSummary.current?.focus() }, [message])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (active.current) return
    const fields: FieldErrors = {}
    if (registering && !/^[A-Za-z0-9_]{1,50}$/.test(username.trim())) {
      fields.username = 'Use 1-50 letters, numbers or underscores.'
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()) || email.trim().length > 254) {
      fields.email = 'Enter a valid email address.'
    }
    const length = Array.from(password).length
    if (length < (registering ? 8 : 1) || length > 128) {
      fields.password = registering ? 'Use 8-128 characters.' : 'Enter your password (up to 128 characters).'
    }
    setErrors(fields)
    if (Object.keys(fields).length) {
      setMessage('Please check the highlighted fields.')
      return
    }
    const controller = new AbortController()
    active.current = controller
    setPending(true)
    setMessage('')
    const values = { username: username.trim(), email: email.trim(), password }
    setPassword('')
    try {
      await onSubmit(values, controller.signal)
    } catch (error) {
      if (controller.signal.aborted) return
      const next: FieldErrors = {}
      if (error instanceof ApiError) {
        for (const issue of error.details) {
          const field = issue.loc[1]
          if (field === 'email' || field === 'username' || field === 'password') next[field] = issue.msg
        }
        if (error.code === 'EMAIL_ALREADY_EXISTS') next.email = error.message
        if (error.code === 'USERNAME_ALREADY_EXISTS') next.username = error.message
        setMessage(error.message)
      } else {
        setMessage('Could not complete the request. Please try again.')
      }
      setErrors(next)
    } finally {
      values.password = ''
      active.current = null
      if (!controller.signal.aborted) setPending(false)
    }
  }

  return <form className="auth-form" onSubmit={submit} noValidate aria-busy={pending}>
    {message && <div className="form-error" role="alert" tabIndex={-1} ref={errorSummary}>{message}</div>}
    {registering && <div className="field">
      <label htmlFor="username">Username</label>
      <input id="username" name="username" autoComplete="username" required disabled={pending}
        value={username} onChange={(e) => setUsername(e.target.value)}
        aria-invalid={!!errors.username} aria-describedby={errors.username ? 'username-error' : undefined} />
      {errors.username && <p className="field-error" id="username-error">{errors.username}</p>}
    </div>}
    <div className="field">
      <label htmlFor="email">Email</label>
      <input id="email" name="email" type="email" autoComplete="email" required disabled={pending}
        value={email} onChange={(e) => setEmail(e.target.value)}
        aria-invalid={!!errors.email} aria-describedby={errors.email ? 'email-error' : undefined} />
      {errors.email && <p className="field-error" id="email-error">{errors.email}</p>}
    </div>
    <div className="field">
      <label htmlFor="password">Password</label>
      <div className="password-input">
        <input id="password" name="password" type={showPassword ? 'text' : 'password'} required disabled={pending}
          autoComplete={registering ? 'new-password' : 'current-password'}
          value={password} onChange={(e) => setPassword(e.target.value)}
          aria-invalid={!!errors.password} aria-describedby={errors.password ? 'password-error' : undefined} />
        <button type="button" disabled={pending} onClick={() => setShowPassword((visible) => !visible)} aria-label={showPassword ? 'Hide password' : 'Show password'}>{showPassword ? 'Hide' : 'Show'}</button>
      </div>
      {errors.password && <p className="field-error" id="password-error">{errors.password}</p>}
    </div>
    <button type="submit" className="primary-button" disabled={pending}>
      {pending ? (registering ? 'Creating account...' : 'Signing in...') :
        (registering ? 'Create account' : 'Log in')}
    </button>
  </form>
}
