export type TripPlace = {
  id: number
  trip_id: number
  proposed_by_user_id: number
  name: string
  address: string | null
  latitude: number
  longitude: number
  provider: string
  provider_place_id: string | null
  note: string | null
  version: number
  created_at: string
  updated_at: string
}

export type PlaceInput = {
  name: string
  latitude: number
  longitude: number
  address?: string | null
  note?: string | null
  // Send both for a saved search result; omit both for a manual place.
  provider?: string
  provider_place_id?: string
}

// Coordinates are immutable after creation, so only these fields can change.
export type PlaceUpdate = Partial<Pick<TripPlace, 'name' | 'address' | 'note'>>

export type GeocodeResult = {
  provider: string
  provider_place_id: string
  name: string
  address: string | null
  latitude: number
  longitude: number
}

export type RouteStop = {
  item_id: number
  place_id: number
  name: string
  latitude: number
  longitude: number
}

export type RouteLeg = {
  from_item_id: number
  to_item_id: number
  distance_km: number
}

/** Straight-line distances between consecutive located items of one day. */
export type DayRoute = {
  date: string
  stops: RouteStop[]
  legs: RouteLeg[]
  total_distance_km: number
  unlocated_item_ids: number[]
}

/** A suggestion only; nothing is saved until the client applies it via reorder. */
export type OptimizePlan = {
  date: string
  keep_first: boolean
  changed: boolean
  original_item_ids: number[]
  proposed_item_ids: number[]
  anchored_item_ids: number[]
  original_route: DayRoute
  proposed_route: DayRoute
}
