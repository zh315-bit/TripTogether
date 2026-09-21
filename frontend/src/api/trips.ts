import { ApiError } from './client'
import type { AuthenticatedRequest, Trip, TripInput } from '../types/trip'

function parseTrip(body: unknown): Trip {
  if (
    typeof body !== 'object' || body === null ||
    !('id' in body) || typeof body.id !== 'number' ||
    !('name' in body) || typeof body.name !== 'string' ||
    !('destination' in body) || typeof body.destination !== 'string' ||
    !('start_date' in body) || typeof body.start_date !== 'string' ||
    !('end_date' in body) || typeof body.end_date !== 'string' ||
    !('owner_id' in body) || typeof body.owner_id !== 'number' ||
    !('created_at' in body) || typeof body.created_at !== 'string' ||
    !('updated_at' in body) || typeof body.updated_at !== 'string'
  ) {
    throw new ApiError(200, 'INVALID_RESPONSE', 'Unexpected trip response.')
  }
  return {
    id: body.id,
    name: body.name,
    destination: body.destination,
    start_date: body.start_date,
    end_date: body.end_date,
    owner_id: body.owner_id,
    created_at: body.created_at,
    updated_at: body.updated_at,
  }
}

export async function listTrips(request: AuthenticatedRequest): Promise<Trip[]> {
  const body = await request<unknown>('/api/v1/trips')
  if (!Array.isArray(body)) {
    throw new ApiError(200, 'INVALID_RESPONSE', 'Unexpected trips response.')
  }
  return body.map(parseTrip)
}

export async function getTrip(
  request: AuthenticatedRequest,
  tripId: string,
): Promise<Trip> {
  return parseTrip(await request<unknown>(`/api/v1/trips/${encodeURIComponent(tripId)}`))
}

export async function createTrip(
  request: AuthenticatedRequest,
  payload: TripInput,
): Promise<Trip> {
  return parseTrip(await request<unknown>('/api/v1/trips', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }))
}

export async function updateTrip(
  request: AuthenticatedRequest,
  tripId: string,
  payload: Partial<TripInput>,
): Promise<Trip> {
  return parseTrip(await request<unknown>(`/api/v1/trips/${encodeURIComponent(tripId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }))
}

export function deleteTrip(
  request: AuthenticatedRequest,
  tripId: string,
): Promise<void> {
  return request<void>(`/api/v1/trips/${encodeURIComponent(tripId)}`, {
    method: 'DELETE',
  })
}
