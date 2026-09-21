import type { AuthenticatedRequest } from './trip'

export type TripMember = {
  user_id: number
  username: string
  email: string
  role: 'owner' | 'member'
  joined_at: string
}

export type InvitationStatus = 'pending' | 'accepted' | 'rejected'

export type Invitation = {
  id: number
  trip_id: number
  inviter_id: number
  invitee_id: number
  status: InvitationStatus
  created_at: string
  responded_at: string | null
}

export type ItineraryItem = {
  id: number
  trip_id: number
  title: string
  location: string | null
  date: string
  start_time: string | null
  end_time: string | null
  notes: string | null
  position: number
  created_by_user_id: number
  created_at: string
  updated_at: string
}

export type ItineraryInput = {
  title: string
  date: string
  location: string | null
  start_time: string | null
  end_time: string | null
  notes: string | null
}

export type { AuthenticatedRequest }
