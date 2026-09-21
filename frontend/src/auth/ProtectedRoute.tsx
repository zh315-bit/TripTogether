import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from './AuthContext'
import { LogoutButton } from '../components/LogoutButton'

export function SessionStatus() {
  const { state, restore } = useAuth()
  if (state.status === 'loading') return <p role="status">Checking session...</p>
  if (state.status !== 'error') return null
  return <section className="session-error">
    <p role="alert">{state.message}</p>
    <div className="actions">
      <button className="retry-button" onClick={() => void restore()}>Retry session</button>
      <LogoutButton />
    </div>
  </section>
}

export function ProtectedRoute() {
  const { state } = useAuth()
  if (state.status === 'loading' || state.status === 'error') return <SessionStatus />
  return state.status === 'authenticated' ? <Outlet /> : <Navigate to="/login" replace />
}
