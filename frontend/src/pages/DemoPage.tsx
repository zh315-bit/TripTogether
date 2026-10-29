import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import type { DemoMember } from '../types/auth'

export const DEMO_MEMBERS: readonly DemoMember[] = ['mika', 'jonas', 'aiko']
export const DEMO_NAMES: Record<DemoMember, string> = { mika: 'Mika', jonas: 'Jonas', aiko: 'Aiko' }

function describe(error: unknown): string {
  if (error instanceof ApiError && error.code === 'DEMO_DISABLED') return 'The demo is not enabled on this server.'
  if (error instanceof ApiError && error.status === 429) return 'Too many demo sign-ins right now; try again in a minute.'
  return error instanceof ApiError ? error.message : 'Could not start the demo.'
}

/** Signs in as a demo member and opens the shared demo trip. */
function useDemo(member: DemoMember) {
  const { loginDemo } = useAuth()
  const navigate = useNavigate()
  const [pending, setPending] = useState(false)
  const [message, setMessage] = useState('')
  const controller = useRef<AbortController | null>(null)

  useEffect(() => () => controller.current?.abort(), [])

  async function start() {
    if (pending) return
    controller.current?.abort()
    const current = new AbortController()
    controller.current = current
    setPending(true)
    setMessage('')
    try {
      await loginDemo(member, current.signal, (tripId) => navigate(`/trips/${tripId}`, { replace: true }))
    } catch (error) {
      if (current.signal.aborted) return
      setMessage(describe(error))
      setPending(false)
    }
  }
  return { start, pending, message }
}

export function TryDemoButton() {
  const { start, pending, message } = useDemo('mika')
  return <>
    <button className="primary-button" type="button" disabled={pending} onClick={() => void start()}>
      {pending ? 'Opening the demo...' : 'Try the demo'}
    </button>
    {message && <p className="form-error landing-demo-error" role="alert">{message}</p>}
  </>
}

/**
 * `/demo?as=jonas` opens this tab as another demo member: a second window
 * beside the first shows live updates and conflict handling for real.
 */
export function DemoPage() {
  const [params] = useSearchParams()
  const requested = params.get('as') ?? 'mika'
  const member = (DEMO_MEMBERS as readonly string[]).includes(requested) ? requested as DemoMember : 'mika'
  const { state } = useAuth()
  const { start, message } = useDemo(member)
  const started = useRef(false)

  useEffect(() => {
    // Wait for the session restore on mount, which would otherwise abort this sign-in.
    if (started.current || state.status === 'loading') return
    started.current = true
    void start()
    // start is stable for the life of this page; it must run exactly once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.status])

  return <section className="auth-card" aria-labelledby="demo-title">
    <p className="eyebrow">Demo</p>
    <h1 id="demo-title">Signing in as {DEMO_NAMES[member]}...</h1>
    {message
      ? <div className="inline-error" role="alert"><p>{message}</p><Link className="text-link" to="/">Return home</Link></div>
      : <p className="muted-copy" role="status">Opening the shared Kyoto trip.</p>}
  </section>
}
