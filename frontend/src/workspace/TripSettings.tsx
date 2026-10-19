import { useState } from 'react'
import { ApiError } from '../api/client'
import { deleteTrip, updateTrip } from '../api/trips'
import { useAuth } from '../auth/AuthContext'
import { TripForm } from '../components/TripForm'
import type { Trip } from '../types/trip'

type Props = {
  trip: Trip
  owner: boolean
  onUpdated: (trip: Trip) => void
  onDeleted: (tripId: number) => void
}

/** Trip facts for everyone; edit and delete for the owner only (the API enforces it too). */
export function TripSettings({ trip, owner, onUpdated, onDeleted }: Props) {
  const { request } = useAuth()
  const [mode, setMode] = useState<'view' | 'edit' | 'confirm-delete'>('view')
  const [pending, setPending] = useState(false)
  const [message, setMessage] = useState('')

  async function remove() {
    setPending(true)
    setMessage('')
    try {
      await deleteTrip(request, String(trip.id))
      onDeleted(trip.id)
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : 'Could not delete this trip.')
      setMode('view')
    } finally {
      setPending(false)
    }
  }

  if (mode === 'edit') {
    return <section className="panel-section" aria-labelledby="edit-trip-title">
      <h3 id="edit-trip-title">Edit trip</h3>
      <TripForm
        initialValue={{ name: trip.name, destination: trip.destination, start_date: trip.start_date, end_date: trip.end_date }}
        submitLabel="Save changes"
        pendingLabel="Saving changes..."
        onCancel={() => setMode('view')}
        onSubmit={async (value) => {
          onUpdated(await updateTrip(request, String(trip.id), value))
          setMode('view')
        }}
      />
    </section>
  }

  return <section className="panel-section" aria-labelledby="trip-settings-title">
    <h3 id="trip-settings-title">Trip details</h3>
    <dl className="trip-facts">
      <div><dt>Destination</dt><dd>{trip.destination}</dd></div>
      <div><dt>Dates</dt><dd>{trip.start_date} – {trip.end_date}</dd></div>
      <div><dt>Your role</dt><dd>{owner ? 'Trip owner' : 'Trip member'}</dd></div>
    </dl>
    {message && <p className="form-error" role="alert">{message}</p>}
    {owner ? <>
      {mode === 'confirm-delete' ? <div className="confirm-box" role="alertdialog" aria-labelledby="delete-trip-text">
        <p id="delete-trip-text">Delete {trip.name}? Its itinerary, places, expenses and memberships are removed for everyone.</p>
        <div className="actions">
          <button className="danger-button" type="button" disabled={pending} onClick={() => void remove()}>
            {pending ? 'Deleting trip...' : 'Delete trip'}</button>
          <button className="retry-button" type="button" disabled={pending} onClick={() => setMode('view')}>Keep trip</button>
        </div>
      </div> : <div className="actions">
        <button className="primary-button" type="button" onClick={() => setMode('edit')}>Edit trip</button>
        <button className="danger-button" type="button" onClick={() => setMode('confirm-delete')}>Delete trip</button>
      </div>}
    </> : <p className="muted-copy">Only the trip owner can edit or delete this trip.</p>}
  </section>
}
