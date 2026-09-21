import { useEffect, useState } from 'react'
import { ApiError, getHealth } from '../api/client'

type ConnectionState =
  | { status: 'loading' }
  | { status: 'success' }
  | { status: 'error'; message: string }

export function BackendStatus() {
  const [state, setState] = useState<ConnectionState>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    void getHealth(controller.signal).then(
      () => {
        if (!controller.signal.aborted) setState({ status: 'success' })
      },
      (error: unknown) => {
        if (!controller.signal.aborted) {
          setState({
            status: 'error',
            message: error instanceof ApiError ? error.message : 'The backend could not be reached.',
          })
        }
      },
    )
    return () => controller.abort()
  }, [attempt])

  function retry() {
    setState({ status: 'loading' })
    setAttempt((value) => value + 1)
  }

  return (
    <section className="backend-status" aria-labelledby="backend-heading">
      <h2 id="backend-heading">Backend</h2>
      <div className={`status-row ${state.status}`} role="status" aria-live="polite">
        <span className="status-dot" aria-hidden="true" />
        <span>
          {state.status === 'loading' ? 'Checking...' :
            state.status === 'success' ? 'Connected' : 'Unavailable'}
        </span>
      </div>
      {state.status === 'error' && (
        <>
          <p className="error-message">{state.message}</p>
          <button className="retry-button" type="button" onClick={retry}>
            Retry connection
          </button>
        </>
      )}
    </section>
  )
}
