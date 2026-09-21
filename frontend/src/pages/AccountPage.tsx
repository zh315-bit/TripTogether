import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { LogoutButton } from '../components/LogoutButton'

export function AccountPage() {
  const { state } = useAuth()
  if (state.status !== 'authenticated') return null
  return <section className="account-page">
    <h1>Your account</h1>
    <p className="intro-copy">Signed in as</p>
    <dl className="account-details">
      <dt>Username</dt><dd>{state.user.username}</dd>
      <dt>Email</dt><dd>{state.user.email}</dd>
    </dl>
    <Link className="text-link" to="/trips">View trips</Link>
    <LogoutButton />
  </section>
}
