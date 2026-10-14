import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError } from '../../api/client'
import { listItinerary, listMembers, reorderItinerary } from '../../api/collaboration'
import {
  createPlace, deletePlace, getDayRoute, listPlaces, optimizeDay, updatePlace,
} from '../../api/places'
import { useAuth } from '../../auth/AuthContext'
import type { ItineraryItem, TripMember } from '../../types/collaboration'
import type { DayRoute, GeocodeResult, OptimizePlan, PlaceInput, PlaceUpdate, TripPlace } from '../../types/places'
import type { Trip } from '../../types/trip'
import { memberStyle, memberStyles } from '../../utils/memberColors'
import { DayRoutePanel } from './DayRoutePanel'
import { tripDays } from './days'
import { errorCode, errorText } from './errorText'
import { LeafletMap } from './LeafletMap'
import type { LatLng, MapLine, MapMarker } from './LeafletMap'
import { PlacePool } from './PlacePool'
import { PlaceSearch } from './PlaceSearch'
import './MapPanel.css'

const ROUTE_COLOR = '#17233a'
const SUGGESTED_COLOR = '#c2410c'
const CONFLICT_MESSAGE =
  'This day was changed by another member. The latest itinerary has been loaded; suggest again for a fresh order.'

/**
 * Data flow: places, members and itinerary are loaded once; the selected day's
 * route is loaded per day. Optimization returns a plan that is only previewed
 * until the user applies it through the guarded reorder endpoint.
 */
export default function MapPanel({ trip }: { trip: Trip }) {
  const { request } = useAuth()
  const tripId = String(trip.id)
  const [members, setMembers] = useState<TripMember[]>([])
  const [places, setPlaces] = useState<TripPlace[]>([])
  const [items, setItems] = useState<ItineraryItem[]>([])
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [loadMessage, setLoadMessage] = useState('')
  const [notice, setNotice] = useState('')
  const [picking, setPicking] = useState(false)
  const [picked, setPicked] = useState<LatLng | null>(null)
  const [day, setDay] = useState(trip.start_date)
  const [route, setRoute] = useState<DayRoute | null>(null)
  const [plan, setPlan] = useState<OptimizePlan | null>(null)
  const [keepFirst, setKeepFirst] = useState(true)
  const [pending, setPending] = useState<'route' | 'suggest' | 'apply' | null>(null)
  const [routeMessage, setRouteMessage] = useState('')

  const load = useCallback(async () => {
    setStatus('loading')
    try {
      const [nextMembers, nextPlaces, nextItems] = await Promise.all([
        listMembers(request, tripId), listPlaces(request, tripId), listItinerary(request, tripId),
      ])
      setMembers(nextMembers)
      setPlaces(nextPlaces)
      setItems(nextItems)
      setStatus('ready')
    } catch (error) {
      setStatus('error')
      setLoadMessage(errorText(error, 'Could not load the map data.'))
    }
  }, [request, tripId])

  const loadRoute = useCallback(async () => {
    setPending('route')
    try {
      setRoute(await getDayRoute(request, tripId, day))
    } catch (error) {
      setRoute(null)
      setRouteMessage(errorText(error, 'Could not load the route.'))
    } finally {
      setPending(null)
    }
  }, [request, tripId, day])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    setPlan(null)
    setRouteMessage('')
    void loadRoute()
  }, [loadRoute])

  const styles = useMemo(() => memberStyles(members), [members])
  const itemsById = useMemo(() => new Map(items.map((item) => [item.id, item])), [items])

  const markers = useMemo<MapMarker[]>(() => [
    ...places.map((place) => {
      const style = memberStyle(styles, place.proposed_by_user_id)
      return {
        id: `place-${place.id}`, position: [place.latitude, place.longitude] as LatLng, kind: 'place' as const,
        label: style.initial, color: style.color, tooltip: `${place.name} — proposed by ${style.name}`,
      }
    }),
    ...(route?.stops ?? []).map((stop, index) => ({
      id: `stop-${stop.item_id}`, position: [stop.latitude, stop.longitude] as LatLng, kind: 'stop' as const,
      label: String(index + 1), color: ROUTE_COLOR,
      tooltip: `${index + 1}. ${itemsById.get(stop.item_id)?.title ?? stop.name} (${stop.name})`,
    })),
  ], [places, styles, route, itemsById])

  const lines = useMemo<MapLine[]>(() => {
    const result: MapLine[] = []
    if (route) result.push({ id: 'route', color: ROUTE_COLOR, positions: route.stops.map((s) => [s.latitude, s.longitude]) })
    if (plan?.changed) {
      result.push({
        id: 'suggested', color: SUGGESTED_COLOR, dashed: true,
        positions: plan.proposed_route.stops.map((s) => [s.latitude, s.longitude]),
      })
    }
    return result
  }, [route, plan])

  const pick = useCallback((position: LatLng) => {
    setPicked(position)
    setPicking(false)
  }, [])

  async function addResult(result: GeocodeResult): Promise<string> {
    try {
      const created = await createPlace(request, tripId, {
        name: result.name, address: result.address, latitude: result.latitude, longitude: result.longitude,
        provider: result.provider, provider_place_id: result.provider_place_id,
      })
      setPlaces((current) => [...current, created])
      return `${created.name} added to the place pool.`
    } catch (error) {
      if (errorCode(error) === 'PLACE_DUPLICATE') return `${result.name} is already in the place pool.`
      return errorText(error, 'Could not add the place.')
    }
  }

  async function createManual(payload: PlaceInput) {
    const created = await createPlace(request, tripId, payload)
    setPlaces((current) => [...current, created])
    setPicked(null)
    setNotice(`${created.name} added to the place pool.`)
  }

  async function update(place: TripPlace, payload: PlaceUpdate) {
    const updated = await updatePlace(request, tripId, place.id, payload)
    setPlaces((current) => current.map((candidate) => candidate.id === updated.id ? updated : candidate))
    setNotice(`${updated.name} saved.`)
  }

  async function remove(place: TripPlace) {
    await deletePlace(request, tripId, place.id)
    const linked = items.filter((item) => item.place_id === place.id).length
    setPlaces((current) => current.filter((candidate) => candidate.id !== place.id))
    // The server cleared the links; mirror that locally and refresh the route.
    setItems((current) => current.map((item) => item.place_id === place.id ? { ...item, place_id: null } : item))
    setNotice(linked > 0
      ? `${place.name} deleted. ${linked} itinerary item${linked === 1 ? ' was' : 's were'} unlinked; location text was kept.`
      : `${place.name} deleted.`)
    await loadRoute()
  }

  async function suggest() {
    setPending('suggest')
    setRouteMessage('')
    setPlan(null)
    try {
      const next = await optimizeDay(request, tripId, day, keepFirst)
      setPlan(next)
      if (!next.changed) setRouteMessage('The current order is already a short route (straight-line).')
    } catch (error) {
      setRouteMessage(errorText(error, 'Could not suggest an order.'))
    } finally {
      setPending(null)
    }
  }

  async function apply() {
    if (!plan) return
    setPending('apply')
    setRouteMessage('')
    try {
      await reorderItinerary(request, tripId, plan.date, plan.proposed_item_ids, plan.original_item_ids)
      setPlan(null)
      setRouteMessage('Suggested order applied.')
    } catch (error) {
      setPlan(null)
      // No automatic retry: the user reviews the newer order first.
      setRouteMessage(error instanceof ApiError && error.code === 'ITINERARY_CONFLICT'
        ? CONFLICT_MESSAGE : errorText(error, 'Could not apply the order.'))
    } finally {
      setPending(null)
    }
    setItems(await listItinerary(request, tripId).catch(() => items))
    await loadRoute()
  }

  if (status === 'loading') return <p role="status">Loading map data...</p>
  if (status === 'error') return <div className="inline-error" role="alert"><p>{loadMessage}</p>
    <button className="retry-button" type="button" onClick={() => void load()}>Try again</button></div>

  return <section className="collab-section map-section" aria-labelledby="map-section-title">
    <div className="section-heading">
      <div><p className="eyebrow">Plan together</p><h2 id="map-section-title">Map</h2></div>
    </div>
    <div className="map-layout">
      <div className="map-stage">
        <LeafletMap markers={markers} lines={lines} onPick={picking ? pick : undefined}
          label="Trip map with proposed places and the selected day's route" />
        {picking && <p className="map-status" role="status">Click the map to set the new place's coordinates.</p>}
        <ul className="member-legend" aria-label="Member colours">
          {members.map((member) => {
            const style = memberStyle(styles, member.user_id)
            return <li key={member.user_id}><span className="member-swatch" style={{ background: style.color }}
              aria-hidden="true">{style.initial}</span>{member.username}</li>
          })}
        </ul>
      </div>
      <div className="map-sidebar">
        {notice && <p className="success-message" role="status">{notice}</p>}
        <PlaceSearch onAdd={addResult} />
        <PlacePool places={places} styles={styles} picking={picking} picked={picked}
          onTogglePicking={() => setPicking((value) => !value)}
          onCreate={createManual} onUpdate={update} onDelete={remove} />
        <DayRoutePanel days={tripDays(trip.start_date, trip.end_date)} day={day} onDay={setDay}
          route={route} plan={plan} itemsById={itemsById} keepFirst={keepFirst} onKeepFirst={setKeepFirst}
          pending={pending} message={routeMessage} onSuggest={() => void suggest()}
          onApply={() => void apply()} onCancel={() => { setPlan(null); setRouteMessage('') }} />
      </div>
    </div>
  </section>
}
