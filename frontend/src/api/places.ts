import { ApiError } from './client'
import { ifMatch } from './trips'
import type { AuthenticatedRequest } from '../types/trip'
import type {
  DayRoute, GeocodeResult, OptimizePlan, PlaceInput, PlaceUpdate, RouteLeg, RouteStop, TripPlace,
} from '../types/places'

function invalid(field: string): never {
  throw new ApiError(200, 'INVALID_RESPONSE', `Unexpected map field: ${field}.`)
}

function object(body: unknown, field: string): Record<string, unknown> {
  if (typeof body !== 'object' || body === null || Array.isArray(body)) invalid(field)
  return body as Record<string, unknown>
}

function text(value: unknown, field: string): string {
  return typeof value === 'string' ? value : invalid(field)
}

function nullableText(value: unknown, field: string): string | null {
  return value === null ? null : text(value, field)
}

function number(value: unknown, field: string): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : invalid(field)
}

function ids(value: unknown, field: string): number[] {
  return Array.isArray(value) ? value.map((entry) => number(entry, field)) : invalid(field)
}

function list<T>(body: unknown, parse: (value: unknown) => T, field: string): T[] {
  return Array.isArray(body) ? body.map(parse) : invalid(field)
}

function coordinate(value: unknown, field: string, limit: number): number {
  const parsed = number(value, field)
  return Math.abs(parsed) <= limit ? parsed : invalid(field)
}

export function parsePlace(body: unknown): TripPlace {
  const value = object(body, 'place')
  return {
    id: number(value.id, 'id'),
    trip_id: number(value.trip_id, 'trip_id'),
    proposed_by_user_id: number(value.proposed_by_user_id, 'proposed_by_user_id'),
    name: text(value.name, 'name'),
    address: nullableText(value.address, 'address'),
    latitude: coordinate(value.latitude, 'latitude', 90),
    longitude: coordinate(value.longitude, 'longitude', 180),
    provider: text(value.provider, 'provider'),
    provider_place_id: nullableText(value.provider_place_id, 'provider_place_id'),
    note: nullableText(value.note, 'note'),
    version: number(value.version, 'version'),
    created_at: text(value.created_at, 'created_at'),
    updated_at: text(value.updated_at, 'updated_at'),
  }
}

function parseGeocodeResult(body: unknown): GeocodeResult {
  const value = object(body, 'result')
  return {
    provider: text(value.provider, 'provider'),
    provider_place_id: text(value.provider_place_id, 'provider_place_id'),
    name: text(value.name, 'name'),
    address: nullableText(value.address, 'address'),
    latitude: coordinate(value.latitude, 'latitude', 90),
    longitude: coordinate(value.longitude, 'longitude', 180),
  }
}

function parseStop(body: unknown): RouteStop {
  const value = object(body, 'stop')
  return {
    item_id: number(value.item_id, 'item_id'),
    place_id: number(value.place_id, 'place_id'),
    name: text(value.name, 'name'),
    latitude: coordinate(value.latitude, 'latitude', 90),
    longitude: coordinate(value.longitude, 'longitude', 180),
  }
}

function parseLeg(body: unknown): RouteLeg {
  const value = object(body, 'leg')
  return {
    from_item_id: number(value.from_item_id, 'from_item_id'),
    to_item_id: number(value.to_item_id, 'to_item_id'),
    distance_km: number(value.distance_km, 'distance_km'),
  }
}

export function parseRoute(body: unknown): DayRoute {
  const value = object(body, 'route')
  return {
    date: text(value.date, 'date'),
    stops: list(value.stops, parseStop, 'stops'),
    legs: list(value.legs, parseLeg, 'legs'),
    total_distance_km: number(value.total_distance_km, 'total_distance_km'),
    unlocated_item_ids: ids(value.unlocated_item_ids, 'unlocated_item_ids'),
  }
}

function parsePlan(body: unknown): OptimizePlan {
  const value = object(body, 'plan')
  if (typeof value.changed !== 'boolean' || typeof value.keep_first !== 'boolean') invalid('changed')
  return {
    date: text(value.date, 'date'),
    keep_first: value.keep_first,
    changed: value.changed,
    original_item_ids: ids(value.original_item_ids, 'original_item_ids'),
    proposed_item_ids: ids(value.proposed_item_ids, 'proposed_item_ids'),
    anchored_item_ids: ids(value.anchored_item_ids, 'anchored_item_ids'),
    original_route: parseRoute(value.original_route),
    proposed_route: parseRoute(value.proposed_route),
  }
}

const placesPath = (tripId: string) => `/api/v1/trips/${encodeURIComponent(tripId)}/places`
const itineraryPath = (tripId: string) => `/api/v1/trips/${encodeURIComponent(tripId)}/itinerary`
const jsonInit = (method: string, body: unknown): RequestInit => ({
  method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
})

export async function listPlaces(request: AuthenticatedRequest, tripId: string): Promise<TripPlace[]> {
  return list(await request<unknown>(placesPath(tripId)), parsePlace, 'places')
}

export async function createPlace(
  request: AuthenticatedRequest, tripId: string, payload: PlaceInput,
): Promise<TripPlace> {
  return parsePlace(await request<unknown>(placesPath(tripId), jsonInit('POST', payload)))
}

export async function updatePlace(
  request: AuthenticatedRequest, tripId: string, placeId: number, payload: PlaceUpdate, version?: number,
): Promise<TripPlace> {
  const init = jsonInit('PATCH', payload)
  return parsePlace(await request<unknown>(`${placesPath(tripId)}/${placeId}`,
    { ...init, headers: { ...init.headers, ...ifMatch(version) } }))
}

export function deletePlace(request: AuthenticatedRequest, tripId: string, placeId: number): Promise<void> {
  return request<void>(`${placesPath(tripId)}/${placeId}`, { method: 'DELETE' })
}

/** Explicit search only: callers must not invoke this per keystroke. */
export async function searchPlaces(
  request: AuthenticatedRequest, query: string, limit = 5,
): Promise<GeocodeResult[]> {
  const params = new URLSearchParams({ q: query, limit: String(limit) })
  return list(await request<unknown>(`/api/v1/geocode?${params}`), parseGeocodeResult, 'results')
}

export async function getDayRoute(
  request: AuthenticatedRequest, tripId: string, date: string,
): Promise<DayRoute> {
  const params = new URLSearchParams({ date })
  return parseRoute(await request<unknown>(`${itineraryPath(tripId)}/route?${params}`))
}

export async function optimizeDay(
  request: AuthenticatedRequest, tripId: string, date: string, keepFirst: boolean,
): Promise<OptimizePlan> {
  return parsePlan(await request<unknown>(
    `${itineraryPath(tripId)}/optimize`, jsonInit('POST', { date, keep_first: keepFirst }),
  ))
}
