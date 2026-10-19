import { Suspense, lazy, useCallback, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { listInvitations } from '../api/collaboration'
import { createTrip, listTrips } from '../api/trips'
import { useAuth } from '../auth/AuthContext'
import { InvitationInbox } from '../components/InvitationInbox'
import { LogoutButton } from '../components/LogoutButton'
import { TripForm } from '../components/TripForm'
import type { Trip } from '../types/trip'
import { Icon } from './Icon'
import './WorkspacePage.css'

// Leaflet and every trip tool load with this chunk, keeping public pages light.
const TripWorkspace = lazy(() => import('./TripWorkspace'))
const LAST_TRIP_KEY = 'triptogether:last-trip'

function rememberTrip(id: number) {
  try { localStorage.setItem(LAST_TRIP_KEY, String(id)) } catch { /* storage is a convenience only */ }
}

function rememberedTrip(trips: Trip[]): Trip | undefined {
  try {
    const id = Number(localStorage.getItem(LAST_TRIP_KEY))
    return trips.find((trip) => trip.id === id)
  } catch {
    return undefined
  }
}

type Menu = 'new-trip' | 'invitations' | 'account' | null

function Popover({ open, onClose, label, children }: {
  open: boolean; onClose: () => void; label: string; children: ReactNode
}) {
  const panel = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    const onPointer = (event: MouseEvent) => {
      const target = event.target as Element | null
      // Clicks on the toggles are handled by their own buttons.
      if (!panel.current?.contains(target) && !target?.closest('[data-popover-toggle]')) onClose()
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onPointer)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onPointer)
    }
  }, [open, onClose])
  if (!open) return null
  return <div ref={panel} className="topbar-popover" role="dialog" aria-label={label}>{children}</div>
}

/**
 * Signed-in home. /trips picks the last opened (or first) trip; /trips/:tripId
 * shows that trip's map workspace. The switcher changes the URL, so every trip
 * view stays linkable.
 */
export function WorkspacePage() {
  const { state, request } = useAuth()
  const { tripId } = useParams()
  const navigate = useNavigate()
  const [trips, setTrips] = useState<Trip[]>([])
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [message, setMessage] = useState('')
  const [pendingInvites, setPendingInvites] = useState(0)
  const [menu, setMenu] = useState<Menu>(null)
  const closeMenu = useCallback(() => setMenu(null), [])

  const load = useCallback(async () => {
    try {
      setTrips(await listTrips(request))
      setStatus('ready')
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) return
      setStatus('error')
      setMessage(error instanceof ApiError ? error.message : 'Could not load your trips.')
    }
  }, [request])

  const loadInvites = useCallback(async () => {
    try {
      setPendingInvites((await listInvitations(request)).filter((item) => item.status === 'pending').length)
    } catch {
      setPendingInvites(0)
    }
  }, [request])

  useEffect(() => {
    void load()
    void loadInvites()
  }, [load, loadInvites])

  const selected = trips.find((trip) => String(trip.id) === tripId)
  useEffect(() => {
    if (selected) rememberTrip(selected.id)
  }, [selected])

  if (state.status !== 'authenticated') return null
  if (status === 'ready' && !tripId && trips.length > 0) {
    return <Navigate to={`/trips/${(rememberedTrip(trips) ?? trips[0]).id}`} replace />
  }

  const toggle = (next: Exclude<Menu, null>) => setMenu((current) => current === next ? null : next)
  const newTripForm = <TripForm
    submitLabel="Create trip"
    pendingLabel="Creating trip..."
    onCancel={trips.length > 0 ? closeMenu : undefined}
    onSubmit={async (value) => {
      const trip = await createTrip(request, value)
      setTrips((current) => [...current, trip].sort((a, b) => a.id - b.id))
      setMenu(null)
      navigate(`/trips/${trip.id}`)
    }}
  />
  const invitationsChanged = () => {
    void load()
    void loadInvites()
  }

  return <div className="workspace-page">
    <header className="workspace-topbar">
      <Link className="topbar-brand" to="/trips"><Icon name="compass" size={22} /><span>TripTogether</span></Link>
      {trips.length > 0 && <div className="trip-switcher">
        <Icon name="pin" />
        <label className="visually-hidden" htmlFor="trip-switcher">Current trip</label>
        <select id="trip-switcher" value={selected ? String(selected.id) : ''}
          onChange={(event) => navigate(`/trips/${event.target.value}`)}>
          {!selected && <option value="" disabled>Choose a trip</option>}
          {trips.map((trip) => <option key={trip.id} value={trip.id}>
            {trip.name} · {trip.start_date.slice(5)} – {trip.end_date.slice(5)}</option>)}
        </select>
      </div>}
      <div className="topbar-anchor">
        <button className="topbar-button" type="button" data-popover-toggle aria-expanded={menu === 'new-trip'}
          onClick={() => toggle('new-trip')}><Icon name="plus" /><span className="topbar-label">New trip</span></button>
        <Popover open={menu === 'new-trip'} onClose={closeMenu} label="Create a trip">
          <h2 className="popover-title">Create a trip</h2>{newTripForm}
        </Popover>
      </div>
      <div className="topbar-end">
        <div className="topbar-anchor">
          <button className="topbar-icon-button" type="button" data-popover-toggle aria-expanded={menu === 'invitations'}
            aria-label={pendingInvites > 0 ? `Invitations, ${pendingInvites} pending` : 'Invitations'}
            onClick={() => toggle('invitations')}>
            <Icon name="bell" />{pendingInvites > 0 && <span className="topbar-badge" aria-hidden="true">{pendingInvites}</span>}
          </button>
          <Popover open={menu === 'invitations'} onClose={closeMenu} label="Invitations">
            <InvitationInbox onChanged={invitationsChanged} />
          </Popover>
        </div>
        <div className="topbar-anchor">
          <button className="topbar-avatar" type="button" data-popover-toggle aria-expanded={menu === 'account'}
            aria-label={`Account menu for ${state.user.username}`} onClick={() => toggle('account')}>
            {state.user.username.slice(0, 1).toUpperCase()}</button>
          <Popover open={menu === 'account'} onClose={closeMenu} label="Account">
            <p className="popover-user"><strong>{state.user.username}</strong><span>{state.user.email}</span></p>
            <div className="popover-actions">
              <Link className="retry-button" to="/account" onClick={closeMenu}>Account</Link>
              <LogoutButton className="retry-button" />
            </div>
          </Popover>
        </div>
      </div>
    </header>

    {status === 'loading' && <p className="workspace-status" role="status">Loading your trips...</p>}
    {status === 'error' && <div className="workspace-status inline-error" role="alert"><p>{message}</p>
      <button className="retry-button" type="button" onClick={() => void load()}>Retry</button></div>}
    {status === 'ready' && trips.length === 0 && <main className="workspace-empty breathing-bg">
      <section className="empty-card" aria-labelledby="first-trip-title">
        <p className="eyebrow">Your travel space</p>
        <h1 id="first-trip-title">Where to first?</h1>
        <p className="intro-copy">Create a trip, invite your people, and plan it together on one shared map.</p>
        {newTripForm}
      </section>
      <section className="empty-card"><InvitationInbox onChanged={invitationsChanged} /></section>
    </main>}
    {status === 'ready' && tripId && !selected && trips.length > 0 && <main className="workspace-status inline-error" role="alert">
      <p>This trip isn't available. It may have been deleted, or you're not a member.</p>
      <Link className="text-link" to="/trips">Open your trips</Link>
    </main>}
    {selected && <Suspense fallback={<p className="workspace-status" role="status">Loading map...</p>}>
      <TripWorkspace key={selected.id} trip={selected} owner={selected.owner_id === state.user.id}
        onTripUpdated={(updated) => setTrips((current) => current.map((trip) => trip.id === updated.id ? updated : trip))}
        onTripDeleted={(id) => {
          setTrips((current) => current.filter((trip) => trip.id !== id))
          try { localStorage.removeItem(LAST_TRIP_KEY) } catch { /* convenience only */ }
          navigate('/trips', { replace: true })
        }} />
    </Suspense>}
  </div>
}
