import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import * as authApi from '../api/auth'
import { ApiError } from '../api/client'

function explain(error: unknown, fallback: string): string {
  if (error instanceof ApiError && error.code === 'PASSWORD_RESET_UNAVAILABLE') {
    return 'Password reset is not available on this server. Ask whoever runs it to configure mail.'
  }
  if (error instanceof ApiError && error.status === 429) return 'Too many attempts; try again in a minute.'
  if (error instanceof ApiError && error.code === 'INVALID_RESET_TOKEN') {
    return 'This reset link is invalid, already used or expired. Request a new one.'
  }
  return error instanceof ApiError ? error.message : fallback
}

function useAbortOnUnmount() {
  const controller = useRef<AbortController | null>(null)
  useEffect(() => () => controller.current?.abort(), [])
  return controller
}

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [pending, setPending] = useState(false)
  const [done, setDone] = useState(false)
  const [message, setMessage] = useState('')
  const controller = useAbortOnUnmount()

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending) return
    controller.current?.abort()
    const current = new AbortController()
    controller.current = current
    setPending(true)
    setMessage('')
    try {
      await authApi.forgotPassword(email.trim(), current.signal)
      if (!current.signal.aborted) setDone(true)
    } catch (error) {
      if (!current.signal.aborted) setMessage(explain(error, 'Could not send the reset link.'))
    } finally {
      if (!current.signal.aborted) setPending(false)
    }
  }

  return <section className="auth-card" aria-labelledby="forgot-title">
    <h1 id="forgot-title">Reset your password</h1>
    {done
      ? <p className="success-message" role="status">If an account exists for that address, a reset link is on its way. It works once and expires in an hour.</p>
      : <form className="auth-form" onSubmit={submit} noValidate>
        <p className="intro-copy">Enter your email and we will send you a link to choose a new password.</p>
        {message && <p className="form-error" role="alert">{message}</p>}
        <div className="field">
          <label htmlFor="forgot-email">Email</label>
          <input id="forgot-email" type="email" autoComplete="email" required disabled={pending}
            value={email} onChange={(event) => setEmail(event.target.value)} />
        </div>
        <button className="primary-button" type="submit" disabled={pending || !email.trim()}>
          {pending ? 'Sending...' : 'Send reset link'}
        </button>
      </form>}
    <p className="auth-switch"><Link to="/login">Back to log in</Link></p>
  </section>
}

export function ResetPasswordPage() {
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [pending, setPending] = useState(false)
  const [done, setDone] = useState(false)
  const [message, setMessage] = useState('')
  const controller = useAbortOnUnmount()

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending) return
    if (password.length < 8 || password.length > 128) {
      setMessage('Use 8-128 characters.')
      return
    }
    if (password !== confirm) {
      setMessage('The two passwords do not match.')
      return
    }
    controller.current?.abort()
    const current = new AbortController()
    controller.current = current
    setPending(true)
    setMessage('')
    try {
      await authApi.resetPassword(token, password, current.signal)
      if (!current.signal.aborted) setDone(true)
    } catch (error) {
      if (!current.signal.aborted) setMessage(explain(error, 'Could not reset the password.'))
    } finally {
      if (!current.signal.aborted) setPending(false)
    }
  }

  if (!token) {
    return <section className="auth-card" aria-labelledby="reset-title">
      <h1 id="reset-title">Choose a new password</h1>
      <p className="form-error" role="alert">This link is missing its token. Open the link from your email, or request a new one.</p>
      <p className="auth-switch"><Link to="/forgot-password">Request a new link</Link></p>
    </section>
  }
  return <section className="auth-card" aria-labelledby="reset-title">
    <h1 id="reset-title">Choose a new password</h1>
    {done
      ? <>
        <p className="success-message" role="status">Your password has been changed and every other session was signed out.</p>
        <p className="auth-switch"><Link className="primary-button" to="/login">Log in</Link></p>
      </>
      : <form className="auth-form" onSubmit={submit} noValidate>
        {message && <p className="form-error" role="alert">{message}</p>}
        <div className="field">
          <label htmlFor="reset-password">New password</label>
          <input id="reset-password" type="password" autoComplete="new-password" required disabled={pending}
            value={password} onChange={(event) => setPassword(event.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="reset-confirm">Confirm new password</label>
          <input id="reset-confirm" type="password" autoComplete="new-password" required disabled={pending}
            value={confirm} onChange={(event) => setConfirm(event.target.value)} />
        </div>
        <button className="primary-button" type="submit" disabled={pending}>
          {pending ? 'Saving...' : 'Set new password'}
        </button>
        <p className="auth-switch"><Link to="/forgot-password">Request a new link</Link></p>
      </form>}
  </section>
}
