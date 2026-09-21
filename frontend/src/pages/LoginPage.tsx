import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { AuthForm } from '../components/AuthForm'
import { useAuth } from '../auth/AuthContext'
import { SessionStatus } from '../auth/ProtectedRoute'

export function LoginPage() {
  const { state, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  if (state.status === 'authenticated') return <Navigate to="/trips" replace />
  if (state.status !== 'anonymous') return <SessionStatus />
  return <section className="auth-card" aria-labelledby="login-title">
    <h1 id="login-title">Log in</h1>
    {location.state?.registered === true && <p className="success-message" role="status">
      Account created. Please sign in.
    </p>}
    <AuthForm mode="login" onSubmit={async ({ email, password }, signal) => {
      await login({ email, password }, signal)
      if (!signal.aborted) navigate('/trips', { replace: true })
    }} />
    <p className="auth-switch">New to TripTogether? <Link to="/register">Create account</Link></p>
  </section>
}
