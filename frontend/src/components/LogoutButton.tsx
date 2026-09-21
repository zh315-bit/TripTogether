import { startTransition } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export function LogoutButton({ className = 'retry-button' }: { className?: string }) {
  const { logout } = useAuth()
  const navigate = useNavigate()
  return <button className={className} type="button" onClick={() => {
    // Keep the auth change and Router's transition in the same update.
    startTransition(() => {
      logout()
      navigate('/', { replace: true })
    })
  }}>Log out</button>
}
