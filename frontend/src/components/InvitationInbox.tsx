import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { acceptInvitation, listInvitations, rejectInvitation } from '../api/collaboration'
import { useAuth } from '../auth/AuthContext'
import type { Invitation } from '../types/collaboration'

export function InvitationInbox({ onChanged }: { onChanged?: () => void }) {
  const { state, request } = useAuth()
  const [invitations, setInvitations] = useState<Invitation[]>([])
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [message, setMessage] = useState('')
  const [pendingId, setPendingId] = useState<number | null>(null)

  const load = useCallback(async () => {
    setStatus('loading')
    try {
      setInvitations(await listInvitations(request))
      setStatus('ready')
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) return
      setStatus('error')
      setMessage(error instanceof ApiError ? error.message : 'Could not load invitations.')
    }
  }, [request])

  useEffect(() => {
    void load()
  }, [load])

  if (state.status !== 'authenticated') return null

  async function respond(invitation: Invitation, action: 'accept' | 'reject') {
    setPendingId(invitation.id)
    setMessage('')
    try {
      const updated = action === 'accept'
        ? await acceptInvitation(request, invitation.id)
        : await rejectInvitation(request, invitation.id)
      setInvitations((current) => current.map((item) => item.id === updated.id ? updated : item))
      onChanged?.()
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : 'Could not update this invitation.')
    } finally {
      setPendingId(null)
    }
  }

  return (
    <section className="collab-section" aria-labelledby="invitations-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Collaboration</p>
          <h2 id="invitations-title">Invitations</h2>
        </div>
        <button className="retry-button" type="button" onClick={() => void load()}>Refresh</button>
      </div>
      {status === 'loading' && <p role="status">Loading invitations...</p>}
      {status === 'error' && <p className="form-error" role="alert">{message}</p>}
      {status === 'ready' && invitations.length === 0 && (
        <p className="muted-copy">No invitations yet.</p>
      )}
      {status === 'ready' && invitations.length > 0 && <div className="invitation-list">
        {invitations.map((invitation) => (
          <div className="invitation-row" key={invitation.id}>
            <div>
              <strong>Trip #{invitation.trip_id}</strong>
              <span className="trip-meta">From user #{invitation.inviter_id}</span>
            </div>
            <div className="actions">
              <span className={`status-badge status-${invitation.status}`}>{invitation.status}</span>
              {invitation.status === 'pending' && <><button
                className="primary-button"
                type="button"
                disabled={pendingId === invitation.id}
                onClick={() => void respond(invitation, 'accept')}
              >Accept</button><button
                className="retry-button"
                type="button"
                disabled={pendingId === invitation.id}
                onClick={() => void respond(invitation, 'reject')}
              >Reject</button></>}
            </div>
          </div>
        ))}
      </div>}
      {message && status === 'ready' && <p className="form-error" role="alert">{message}</p>}
    </section>
  )
}
