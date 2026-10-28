import { useEffect } from 'react'
import type { ItineraryItem } from '../../types/collaboration'
import type { TripPlace } from '../../types/places'
import type { MemberStyle } from '../../utils/memberColors'

type Props = {
  place: TripPlace
  style: MemberStyle
  /** Itinerary items linked to this place, in trip order. */
  items: ItineraryItem[]
  onClose: () => void
  onShowInList: () => void
}

/** Floats over the map for the selected place, so details never need a panel switch. */
export function PlaceDetailCard({ place, style, items, onClose, onShowInList }: Props) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return <section className="place-detail-card" aria-labelledby="place-detail-title">
    <header>
      <span className="member-swatch" style={{ background: style.color }} aria-hidden="true">{style.initial}</span>
      <div>
        <h3 id="place-detail-title">{place.name}</h3>
        <p className="trip-meta">Proposed by {style.name}</p>
      </div>
      <button className="icon-button" type="button" aria-label="Close place details" onClick={onClose}>×</button>
    </header>
    {place.address && <p className="place-detail-address">{place.address}</p>}
    {place.note && <p className="muted-copy">{place.note}</p>}
    <div>
      <h4>In the itinerary</h4>
      {items.length === 0
        ? <p className="muted-copy">Not linked to any itinerary item yet.</p>
        : <ul className="place-detail-items">{items.map((item) => <li key={item.id}>
          <span className="trip-meta">{[item.date, item.start_time?.slice(0, 5)].filter(Boolean).join(' · ')}</span>
          {item.title}
        </li>)}</ul>}
    </div>
    <footer>
      <span className="trip-meta">{place.latitude.toFixed(5)}, {place.longitude.toFixed(5)}</span>
      <button className="retry-button" type="button" onClick={onShowInList}>Show in place list</button>
    </footer>
  </section>
}
