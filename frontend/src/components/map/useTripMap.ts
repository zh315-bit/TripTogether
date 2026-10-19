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
import { errorCode, errorText } from './errorText'
import type { LatLng, MapLine, MapMarker } from './LeafletMap'

const ROUTE_COLOR = '#17233a'
const SUGGESTED_COLOR = '#c2410c'
const CONFLICT_MESSAGE =
  'This day was changed by another member. The latest itinerary has been loaded; suggest again for a fresh order.'

export type RoutePending = 'route' | 'suggest' | 'apply' | null

/**
 * One trip's map state, shared by the sidebar panels and the map canvas.
 * Places, members and itinerary load once; the selected day's route loads per
 * day. An optimize plan is only a preview until applied through guarded reorder.
 */
export function useTripMap(trip: Trip) {
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
  const [pending, setPending] = useState<RoutePending>(null)
  const [routeMessage, setRouteMessage] = useState('')
  // Bumped when the map changes the itinerary itself (apply), so list views reload.
  const [itineraryVersion, setItineraryVersion] = useState(0)

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

  /** Called when the itinerary changed elsewhere (sidebar edits): titles and route. */
  const refreshItinerary = useCallback(async () => {
    setItems(await listItinerary(request, tripId).catch(() => items))
    await loadRoute()
  }, [request, tripId, items, loadRoute])

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
    setItineraryVersion((version) => version + 1)
    await loadRoute()
  }

  function cancelPlan() {
    setPlan(null)
    setRouteMessage('')
  }

  return {
    status, loadMessage, load, notice, members, places, items, itemsById, styles,
    markers, lines, picking, picked, pick, togglePicking: () => setPicking((value) => !value),
    day, setDay, route, plan, keepFirst, setKeepFirst, pending, routeMessage,
    addResult, createManual, update, remove, suggest, apply, cancelPlan, refreshItinerary, itineraryVersion,
  }
}

export type TripMapState = ReturnType<typeof useTripMap>
