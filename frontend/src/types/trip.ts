export type Trip = {
  id: number
  name: string
  destination: string
  start_date: string
  end_date: string
  owner_id: number
  created_at: string
  updated_at: string
}

export type TripInput = {
  name: string
  destination: string
  start_date: string
  end_date: string
}

export type AuthenticatedRequest = <T>(
  path: string,
  init?: RequestInit,
) => Promise<T>
