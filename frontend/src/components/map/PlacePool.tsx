import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import type { PlaceInput, PlaceUpdate, TripPlace } from '../../types/places'
import { memberStyle } from '../../utils/memberColors'
import type { MemberStyle } from '../../utils/memberColors'
import { errorText } from './errorText'
import type { LatLng } from './LeafletMap'

type Props = {
  places: TripPlace[]
  styles: Map<number, MemberStyle>
  picking: boolean
  picked: LatLng | null
  onTogglePicking: () => void
  onCreate: (payload: PlaceInput) => Promise<void>
  onUpdate: (place: TripPlace, payload: PlaceUpdate) => Promise<void>
  onDelete: (place: TripPlace) => Promise<void>
}

function parseCoordinate(value: string, limit: number): number | null {
  // At most six decimals: the server rejects (rather than rounds) more precision.
  if (!/^-?[0-9]{1,3}(\.[0-9]{1,6})?$/.test(value.trim())) return null
  const parsed = Number(value)
  return Math.abs(parsed) <= limit ? parsed : null
}

function ManualPlaceForm({ picking, picked, onTogglePicking, onCreate }: Pick<
  Props, 'picking' | 'picked' | 'onTogglePicking' | 'onCreate'
>) {
  const [name, setName] = useState('')
  const [latitude, setLatitude] = useState('')
  const [longitude, setLongitude] = useState('')
  const [message, setMessage] = useState('')
  const [pending, setPending] = useState(false)

  useEffect(() => {
    if (!picked) return
    setLatitude(picked[0].toFixed(6))
    setLongitude(picked[1].toFixed(6))
  }, [picked])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const lat = parseCoordinate(latitude, 90)
    const lng = parseCoordinate(longitude, 180)
    if (!name.trim()) return setMessage('Name is required.')
    if (lat === null || lng === null) {
      return setMessage('Enter latitude (-90 to 90) and longitude (-180 to 180) with at most six decimals, or pick a point on the map.')
    }
    setPending(true)
    setMessage('')
    try {
      await onCreate({ name: name.trim(), latitude: lat, longitude: lng })
      setName('')
      setLatitude('')
      setLongitude('')
    } catch (error) {
      setMessage(errorText(error, 'Could not add the place.'))
    } finally {
      setPending(false)
    }
  }

  return <form className="map-card manual-place-form" onSubmit={submit} aria-labelledby="manual-place-title">
    <h3 id="manual-place-title">Add a place manually</h3>
    <div className="field"><label htmlFor="manual-place-name">Name</label>
      <input id="manual-place-name" value={name} maxLength={200} disabled={pending}
        onChange={(event) => setName(event.target.value)} /></div>
    <div className="coordinate-grid">
      <div className="field"><label htmlFor="manual-place-lat">Latitude</label>
        <input id="manual-place-lat" inputMode="decimal" value={latitude} disabled={pending}
          onChange={(event) => setLatitude(event.target.value)} /></div>
      <div className="field"><label htmlFor="manual-place-lng">Longitude</label>
        <input id="manual-place-lng" inputMode="decimal" value={longitude} disabled={pending}
          onChange={(event) => setLongitude(event.target.value)} /></div>
    </div>
    {message && <p className="form-error" role="alert">{message}</p>}
    <div className="actions">
      <button className="retry-button" type="button" aria-pressed={picking} onClick={onTogglePicking}>
        {picking ? 'Click the map… (cancel)' : 'Pick on map'}</button>
      <button className="primary-button" type="submit" disabled={pending}>{pending ? 'Adding...' : 'Add place'}</button>
    </div>
  </form>
}

function PlaceRow({ place, style, onUpdate, onDelete }: {
  place: TripPlace
  style: MemberStyle
  onUpdate: Props['onUpdate']
  onDelete: Props['onDelete']
}) {
  const [mode, setMode] = useState<'view' | 'edit' | 'confirm-delete'>('view')
  const [name, setName] = useState(place.name)
  const [note, setNote] = useState(place.note ?? '')
  const [pending, setPending] = useState(false)
  const [message, setMessage] = useState('')

  async function run(action: () => Promise<void>, fallback: string) {
    setPending(true)
    setMessage('')
    try {
      await action()
      setMode('view')
    } catch (error) {
      setMessage(errorText(error, fallback))
    } finally {
      setPending(false)
    }
  }

  return <li className="place-row">
    <span className="member-swatch" style={{ background: style.color }} aria-hidden="true">{style.initial}</span>
    <div className="place-row-body">
      {mode === 'edit' ? <form onSubmit={(event) => {
        event.preventDefault()
        if (!name.trim()) return setMessage('Name is required.')
        void run(() => onUpdate(place, { name: name.trim(), note: note || null }), 'Could not save the place.')
      }}>
        <div className="field"><label htmlFor={`place-name-${place.id}`}>Name</label>
          <input id={`place-name-${place.id}`} value={name} maxLength={200} disabled={pending}
            onChange={(event) => setName(event.target.value)} /></div>
        <div className="field"><label htmlFor={`place-note-${place.id}`}>Note</label>
          <input id={`place-note-${place.id}`} value={note} maxLength={500} disabled={pending}
            onChange={(event) => setNote(event.target.value)} /></div>
        <div className="actions">
          <button className="primary-button" type="submit" disabled={pending}>Save place</button>
          <button className="retry-button" type="button" disabled={pending} onClick={() => setMode('view')}>Cancel</button>
        </div>
      </form> : <>
        <strong>{place.name}</strong>
        <span className="trip-meta">Proposed by {style.name}{place.address ? ` · ${place.address}` : ''}</span>
        {place.note && <p className="muted-copy">{place.note}</p>}
      </>}
      {mode === 'confirm-delete' && <div className="confirm-box" role="alertdialog"
        aria-labelledby={`delete-place-${place.id}`}>
        <p id={`delete-place-${place.id}`}>Delete {place.name}? Itinerary items linked to it will be
          unlinked automatically; their location text stays.</p>
        <div className="actions">
          <button className="danger-button" type="button" disabled={pending}
            onClick={() => void run(() => onDelete(place), 'Could not delete the place.')}>Delete place</button>
          <button className="retry-button" type="button" disabled={pending} onClick={() => setMode('view')}>Keep it</button>
        </div>
      </div>}
      {message && <p className="form-error" role="alert">{message}</p>}
    </div>
    {mode === 'view' && <div className="actions">
      <button className="retry-button" type="button" aria-label={`Edit ${place.name}`} onClick={() => {
        setName(place.name)
        setNote(place.note ?? '')
        setMode('edit')
      }}>Edit</button>
      <button className="danger-button" type="button" aria-label={`Delete ${place.name}`}
        onClick={() => setMode('confirm-delete')}>Delete</button>
    </div>}
  </li>
}

export function PlacePool(props: Props) {
  const { places, styles } = props
  return <section className="map-card" aria-labelledby="place-pool-title">
    <h3 id="place-pool-title">Place pool <span className="count-badge">{places.length}</span></h3>
    {places.length === 0
      ? <p className="muted-copy">No places yet. Search above or add one manually.</p>
      : <ul className="place-list">{places.map((place) => <PlaceRow key={place.id} place={place}
        style={memberStyle(styles, place.proposed_by_user_id)} onUpdate={props.onUpdate} onDelete={props.onDelete} />)}</ul>}
    <ManualPlaceForm picking={props.picking} picked={props.picked}
      onTogglePicking={props.onTogglePicking} onCreate={props.onCreate} />
  </section>
}
