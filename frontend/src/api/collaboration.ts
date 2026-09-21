import { ApiError } from './client'
import type {
  AuthenticatedRequest, Invitation, ItineraryInput, ItineraryItem, TripMember,
} from '../types/collaboration'

function object(body: unknown): Record<string, unknown> {
  if (typeof body !== 'object' || body === null) {
    throw new ApiError(200, 'INVALID_RESPONSE', 'Unexpected collaboration response.')
  }
  return body as Record<string, unknown>
}

function text(value: unknown, field: string): string {
  if (typeof value !== 'string') {
    throw new ApiError(200, 'INVALID_RESPONSE', `Unexpected collaboration field: ${field}.`)
  }
  return value
}

function number(value: unknown, field: string): number {
  if (typeof value !== 'number') {
    throw new ApiError(200, 'INVALID_RESPONSE', `Unexpected collaboration field: ${field}.`)
  }
  return value
}

function nullableText(value: unknown, field: string): string | null {
  if (value !== null && typeof value !== 'string') {
    throw new ApiError(200, 'INVALID_RESPONSE', `Unexpected collaboration field: ${field}.`)
  }
  return value
}

function parseMember(body: unknown): TripMember {
  const value = object(body)
  return {
    user_id: number(value.user_id, 'user_id'),
    username: text(value.username, 'username'),
    email: text(value.email, 'email'),
    role: value.role === 'owner' || value.role === 'member'
      ? value.role : (() => { throw new ApiError(200, 'INVALID_RESPONSE', 'Unexpected member role.') })(),
    joined_at: text(value.joined_at, 'joined_at'),
  }
}

function parseInvitation(body: unknown): Invitation {
  const value = object(body)
  const status = value.status
  if (status !== 'pending' && status !== 'accepted' && status !== 'rejected') {
    throw new ApiError(200, 'INVALID_RESPONSE', 'Unexpected invitation status.')
  }
  return {
    id: number(value.id, 'id'),
    trip_id: number(value.trip_id, 'trip_id'),
    inviter_id: number(value.inviter_id, 'inviter_id'),
    invitee_id: number(value.invitee_id, 'invitee_id'),
    status,
    created_at: text(value.created_at, 'created_at'),
    responded_at: nullableText(value.responded_at, 'responded_at'),
  }
}

function parseItineraryItem(body: unknown): ItineraryItem {
  const value = object(body)
  return {
    id: number(value.id, 'id'),
    trip_id: number(value.trip_id, 'trip_id'),
    title: text(value.title, 'title'),
    location: nullableText(value.location, 'location'),
    date: text(value.date, 'date'),
    start_time: nullableText(value.start_time, 'start_time'),
    end_time: nullableText(value.end_time, 'end_time'),
    notes: nullableText(value.notes, 'notes'),
    position: number(value.position, 'position'),
    created_by_user_id: number(value.created_by_user_id, 'created_by_user_id'),
    created_at: text(value.created_at, 'created_at'),
    updated_at: text(value.updated_at, 'updated_at'),
  }
}

function parseList<T>(body: unknown, parse: (value: unknown) => T, label: string): T[] {
  if (!Array.isArray(body)) {
    throw new ApiError(200, 'INVALID_RESPONSE', `Unexpected ${label} response.`)
  }
  return body.map(parse)
}

export async function listMembers(
  request: AuthenticatedRequest, tripId: string,
): Promise<TripMember[]> {
  return parseList(await request<unknown>(`/api/v1/trips/${encodeURIComponent(tripId)}/members`),
    parseMember, 'members')
}

export async function createInvitation(
  request: AuthenticatedRequest, tripId: string, email: string,
): Promise<Invitation> {
  return parseInvitation(await request<unknown>(
    `/api/v1/trips/${encodeURIComponent(tripId)}/invitations`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email }) },
  ))
}

export async function listInvitations(request: AuthenticatedRequest): Promise<Invitation[]> {
  return parseList(await request<unknown>('/api/v1/invitations'), parseInvitation, 'invitations')
}

async function respondToInvitation(
  request: AuthenticatedRequest, invitationId: number, response: 'accept' | 'reject',
): Promise<Invitation> {
  return parseInvitation(await request<unknown>(
    `/api/v1/invitations/${invitationId}/${response}`, { method: 'POST' },
  ))
}

export function acceptInvitation(
  request: AuthenticatedRequest, invitationId: number,
): Promise<Invitation> {
  return respondToInvitation(request, invitationId, 'accept')
}

export function rejectInvitation(
  request: AuthenticatedRequest, invitationId: number,
): Promise<Invitation> {
  return respondToInvitation(request, invitationId, 'reject')
}

export async function listItinerary(
  request: AuthenticatedRequest, tripId: string,
): Promise<ItineraryItem[]> {
  return parseList(await request<unknown>(
    `/api/v1/trips/${encodeURIComponent(tripId)}/itinerary`,
  ), parseItineraryItem, 'itinerary')
}

export async function createItineraryItem(
  request: AuthenticatedRequest, tripId: string, payload: ItineraryInput,
): Promise<ItineraryItem> {
  return parseItineraryItem(await request<unknown>(
    `/api/v1/trips/${encodeURIComponent(tripId)}/itinerary`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) },
  ))
}

export async function updateItineraryItem(
  request: AuthenticatedRequest, tripId: string, itemId: number, payload: Partial<ItineraryInput>,
): Promise<ItineraryItem> {
  return parseItineraryItem(await request<unknown>(
    `/api/v1/trips/${encodeURIComponent(tripId)}/itinerary/${itemId}`,
    { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) },
  ))
}

export function deleteItineraryItem(
  request: AuthenticatedRequest, tripId: string, itemId: number,
): Promise<void> {
  return request<void>(`/api/v1/trips/${encodeURIComponent(tripId)}/itinerary/${itemId}`, {
    method: 'DELETE',
  })
}

export async function reorderItinerary(
  request: AuthenticatedRequest, tripId: string, date: string, itemIds: number[],
): Promise<ItineraryItem[]> {
  return parseList(await request<unknown>(
    `/api/v1/trips/${encodeURIComponent(tripId)}/itinerary/reorder`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date, item_ids: itemIds }),
    },
  ), parseItineraryItem, 'itinerary')
}
