import { Link, Navigate, useNavigate } from 'react-router-dom'
import { register } from '../api/auth'
import { useAuth } from '../auth/AuthContext'
import { SessionStatus } from '../auth/ProtectedRoute'
import { AuthForm } from '../components/AuthForm'

export function RegisterPage() {
  const { state } = useAuth()
  const navigate = useNavigate()
  if (state.status === 'authenticated') return <Navigate to="/trips" replace />
  if (state.status !== 'anonymous') return <SessionStatus />
  return <section className="auth-card" aria-labelledby="register-title">
    <h1 id="register-title">Create account</h1>
    <AuthForm mode="register" onSubmit={async (values, signal) => {
      await register(values, signal)
      if (!signal.aborted) navigate('/login', { replace: true, state: { registered: true } })
    }} />
    <p className="auth-switch">Already have an account? <Link to="/login">Log in</Link></p>
  </section>
}
