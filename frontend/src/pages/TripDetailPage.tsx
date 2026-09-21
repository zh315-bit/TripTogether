import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { deleteTrip, getTrip, updateTrip } from '../api/trips'
import { TripForm } from '../components/TripForm'
import { ItineraryPanel } from '../components/ItineraryPanel'
import { MembersPanel } from '../components/MembersPanel'
import { ExpensePanel } from '../components/ExpensePanel'
import { BalancePanel } from '../components/BalancePanel'
import { useAuth } from '../auth/AuthContext'
import type { Trip, TripInput } from '../types/trip'

export function TripDetailPage() {
  const { tripId } = useParams()
  const navigate = useNavigate()
  const { state, request } = useAuth()
  const [trip, setTrip] = useState<Trip | null>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [message, setMessage] = useState('')
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteMessage, setDeleteMessage] = useState('')
  const [balanceRefreshKey, setBalanceRefreshKey] = useState(0)
  const [activeTab, setActiveTab] = useState<'overview' | 'itinerary' | 'expenses' | 'members'>('overview')
  const tabs = ['overview', 'itinerary', 'expenses', 'members'] as const

  const load = useCallback(async () => {
    if (!tripId) return
    setStatus('loading')
    try {
      setTrip(await getTrip(request, tripId))
      setStatus('ready')
    } catch (error) {
      setStatus('error')
      setMessage(error instanceof ApiError ? error.message : 'Could not load this trip.')
    }
  }, [request, tripId])

  useEffect(() => {
    void load()
  }, [load])

  if (state.status !== 'authenticated') return null
  if (status === 'loading') return <p role="status">Loading trip...</p>
  if (status === 'error' || !trip) return <section className="inline-error" role="alert">
    <p>{message || 'Trip not found.'}</p>
    <Link className="text-link" to="/trips">Back to trips</Link>
  </section>

  const owner = trip.owner_id === state.user.id
  const initialValue: TripInput = {
    name: trip.name,
    destination: trip.destination,
    start_date: trip.start_date,
    end_date: trip.end_date,
  }

  return (
    <section className="trip-detail" aria-labelledby="trip-detail-title">
      <Link className="back-link" to="/trips">← Back to trips</Link>
      {editing ? <section className="trip-editor" aria-labelledby="edit-trip-title">
        <h1 id="edit-trip-title">Edit trip</h1>
        <TripForm
          initialValue={initialValue}
          submitLabel="Save changes"
          pendingLabel="Saving changes..."
          onCancel={() => setEditing(false)}
          onSubmit={async (value) => {
            const updated = await updateTrip(request, String(trip.id), value)
            setTrip(updated)
            setEditing(false)
          }}
        />
      </section> : <>
        <div className="page-heading">
          <div>
            <p className="eyebrow">Trip details</p>
            <h1 id="trip-detail-title">{trip.name}</h1>
            <p className="intro-copy">{trip.destination}</p>
          </div>
          {owner && <div className="actions">
            <button className="primary-button" type="button" onClick={() => setEditing(true)}>Edit trip</button>
            <button className="danger-button" type="button" disabled={deleting} onClick={async () => {
              if (!window.confirm(`Delete ${trip.name}?`)) return
              setDeleting(true)
              setDeleteMessage('')
              try {
                await deleteTrip(request, String(trip.id))
                navigate('/trips', { replace: true })
              } catch (error) {
                setDeleteMessage(error instanceof ApiError ? error.message : 'Could not delete this trip.')
              } finally {
                setDeleting(false)
              }
            }}>{deleting ? 'Deleting trip...' : 'Delete trip'}</button>
          </div>}
        </div>
        {deleteMessage && <p className="form-error" role="alert">{deleteMessage}</p>}
        <div className="trip-hero-meta"><span>{trip.destination}</span><span>•</span><span>{trip.start_date} – {trip.end_date}</span><span className="status-badge">{owner ? 'Owner' : 'Member'}</span></div>
        <div className="workspace-tabs" role="tablist" aria-label="Trip workspace" onKeyDown={(event) => {
          if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
          event.preventDefault()
          const currentIndex = tabs.indexOf(activeTab)
          const nextIndex = event.key === 'ArrowRight' ? (currentIndex + 1) % tabs.length : (currentIndex - 1 + tabs.length) % tabs.length
          setActiveTab(tabs[nextIndex])
        }}>
          {tabs.map((tab) => <button key={tab} id={`trip-tab-${tab}`} type="button" role="tab" aria-controls={`trip-panel-${tab}`} aria-selected={activeTab === tab} tabIndex={activeTab === tab ? 0 : -1} className={activeTab === tab ? 'active' : ''} onClick={() => setActiveTab(tab)}>{tab[0].toUpperCase() + tab.slice(1)}</button>)}
        </div>
        <section id={`trip-panel-${activeTab}`} className="workspace-panel" role="tabpanel" aria-labelledby={`trip-tab-${activeTab}`}>
        {activeTab === 'overview' && <section className="detail-overview" aria-labelledby="overview-title">
          <p className="eyebrow">At a glance</p><h2 id="overview-title">Trip overview</h2>
          <dl className="overview-facts"><div><dt>Destination</dt><dd>{trip.destination}</dd></div><div><dt>Dates</dt><dd>{trip.start_date} – {trip.end_date}</dd></div><div><dt>Your role</dt><dd>{owner ? 'Trip owner' : 'Trip member'}</dd></div></dl>
        </section>}
        {activeTab === 'itinerary' && <ItineraryPanel trip={trip} />}
        {activeTab === 'expenses' && <><ExpensePanel
          tripId={String(trip.id)}
          onChanged={() => setBalanceRefreshKey((value) => value + 1)}
        /><BalancePanel tripId={String(trip.id)} refreshKey={balanceRefreshKey} /></>}
        {activeTab === 'members' && <MembersPanel tripId={String(trip.id)} owner={owner} />}
        </section>
      </>}
    </section>
  )
}
