import { Link, useNavigate } from 'react-router-dom'
import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { createTrip, listTrips } from '../api/trips'
import { TripForm } from '../components/TripForm'
import { InvitationInbox } from '../components/InvitationInbox'
import { useAuth } from '../auth/AuthContext'
import type { Trip } from '../types/trip'

export function TripsPage() {
  const { state, request } = useAuth()
  const navigate = useNavigate()
  const [trips, setTrips] = useState<Trip[]>([])
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [message, setMessage] = useState('')
  const [creating, setCreating] = useState(false)

  const load = useCallback(async () => {
    setStatus('loading')
    setMessage('')
    try {
      setTrips(await listTrips(request))
      setStatus('ready')
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) return
      setStatus('error')
      setMessage(error instanceof ApiError ? error.message : 'Could not load trips.')
    }
  }, [request])

  useEffect(() => {
    void load()
  }, [load])

  if (state.status !== 'authenticated') return null

  return (
    <section className="trip-dashboard" aria-labelledby="trips-title">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Your travel space</p>
          <h1 id="trips-title" aria-label="Trips">Your next adventure starts here.</h1>
          <p className="intro-copy">Create a trip, invite your people, and keep the whole journey together.</p>
        </div>
        <button className="primary-button" type="button" onClick={() => setCreating((value) => !value)}>
          {creating ? 'Close form' : 'Create trip'}
        </button>
      </div>

      {creating && <section className="trip-editor" aria-labelledby="create-trip-title">
        <h2 id="create-trip-title">Create a trip</h2>
        <TripForm
          submitLabel="Create trip"
          pendingLabel="Creating trip..."
          onCancel={() => setCreating(false)}
          onSubmit={async (value) => {
            const trip = await createTrip(request, value)
            setTrips((current) => [...current, trip].sort((a, b) => a.id - b.id))
            setCreating(false)
            navigate(`/trips/${trip.id}`)
          }}
        />
      </section>}

      {status === 'loading' && <p role="status">Loading trips...</p>}
      {status === 'error' && <section className="inline-error" role="alert">
        <p>{message}</p>
        <button className="retry-button" type="button" onClick={() => void load()}>Retry</button>
      </section>}
      {status === 'ready' && trips.length === 0 && !creating && (
        <section className="empty-state">
          <h2>No trips yet</h2>
          <p>Create your first trip to start planning together.</p>
          <button className="primary-button" type="button" onClick={() => setCreating(true)}>Create your first trip</button>
        </section>
      )}
      {status === 'ready' && trips.length > 0 && <div className="trip-list" aria-label="Trip list">
        {trips.map((trip) => (
          <Link className="trip-row" to={`/trips/${trip.id}`} key={trip.id}>
            <span className="destination-mark" aria-hidden="true">{trip.destination.slice(0, 1).toUpperCase()}</span>
            <span className="trip-row-content">
              <span className="trip-meta">{trip.destination}</span>
              <strong>{trip.name}</strong>
            </span>
            <span className="trip-card-meta"><span>{trip.start_date} – {trip.end_date}</span><span className="status-badge">{trip.owner_id === state.user.id ? 'Owner' : 'Member'}</span></span>
          </Link>
        ))}
      </div>}
      <InvitationInbox onChanged={() => void load()} />
    </section>
  )
}
