import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError } from '../api/client'
import { createInvitation, listMembers } from '../api/collaboration'
import { useAuth } from '../auth/AuthContext'
import type { TripMember } from '../types/collaboration'

type Props = { tripId: string; owner: boolean }

export function MembersPanel({ tripId, owner }: Props) {
  const { request } = useAuth()
  const [members, setMembers] = useState<TripMember[]>([])
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [message, setMessage] = useState('')
  const [email, setEmail] = useState('')
  const [pending, setPending] = useState(false)

  const load = useCallback(async () => {
    setStatus('loading')
    try {
      setMembers(await listMembers(request, tripId))
      setStatus('ready')
    } catch (error) {
      setStatus('error')
      setMessage(error instanceof ApiError ? error.message : 'Could not load members.')
    }
  }, [request, tripId])

  useEffect(() => {
    void load()
  }, [load])

  async function invite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!email.trim()) {
      setMessage('Enter a registered user email.')
      return
    }
    setPending(true)
    setMessage('')
    try {
      await createInvitation(request, tripId, email.trim())
      setEmail('')
      setMessage('Invitation sent.')
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : 'Could not send invitation.')
    } finally {
      setPending(false)
    }
  }

  return (
    <section className="collab-section" aria-labelledby="members-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">People</p>
          <h2 id="members-title">Members</h2>
        </div>
        <button className="retry-button" type="button" onClick={() => void load()}>Refresh</button>
      </div>
      {status === 'loading' && <p role="status">Loading members...</p>}
      {status === 'error' && <p className="form-error" role="alert">{message}</p>}
      {status === 'ready' && <div className="member-list">
        {members.map((member) => (
          <div className="member-row" key={member.user_id}>
            <div><strong data-initial={member.username.slice(0, 1).toUpperCase()}>{member.username}</strong><span className="trip-meta">{member.email}</span></div>
            <span className="status-badge">{member.role}</span>
          </div>
        ))}
      </div>}
      {owner && <form className="invite-form" onSubmit={invite}>
        <label htmlFor="invite-email">Invite a registered user</label>
        <div className="inline-form">
          <input
            id="invite-email"
            type="email"
            value={email}
            placeholder="friend@example.com"
            disabled={pending}
            onChange={(event) => setEmail(event.target.value)}
          />
          <button className="primary-button" type="submit" disabled={pending}>
            {pending ? 'Sending...' : 'Send invite'}
          </button>
        </div>
      </form>}
      {message && status !== 'error' && <p className={message === 'Invitation sent.' ? 'success-message' : 'form-error'} role="status">{message}</p>}
    </section>
  )
}
