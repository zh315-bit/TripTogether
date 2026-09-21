import { describe, expect, it, vi } from 'vitest'
import { ApiError } from './client'
import { createTrip, deleteTrip, getTrip, listTrips, updateTrip } from './trips'
import type { TripInput } from '../types/trip'

const trip = {
  id: 12,
  name: 'Tokyo',
  destination: 'Japan',
  start_date: '2027-06-10',
  end_date: '2027-06-15',
  owner_id: 7,
  created_at: '2026-09-20T00:00:00Z',
  updated_at: '2026-09-20T00:00:00Z',
}
const input: TripInput = {
  name: trip.name,
  destination: trip.destination,
  start_date: trip.start_date,
  end_date: trip.end_date,
}

describe('trip API adapters', () => {
  it('lists trips through the authenticated request boundary', async () => {
    const request = vi.fn().mockResolvedValue([trip])
    await expect(listTrips(request)).resolves.toEqual([trip])
    expect(request).toHaveBeenCalledWith('/api/v1/trips')
  })

  it('creates, reads, updates and deletes a trip with the contract paths', async () => {
    const request = vi.fn()
      .mockResolvedValueOnce(trip)
      .mockResolvedValueOnce(trip)
      .mockResolvedValueOnce({ ...trip, name: 'Updated Tokyo' })
      .mockResolvedValueOnce(undefined)

    await expect(createTrip(request, input)).resolves.toEqual(trip)
    await expect(getTrip(request, '12')).resolves.toEqual(trip)
    await expect(updateTrip(request, '12', { name: 'Updated Tokyo' }))
      .resolves.toEqual({ ...trip, name: 'Updated Tokyo' })
    await expect(deleteTrip(request, '12')).resolves.toBeUndefined()

    expect(request.mock.calls).toEqual([
      ['/api/v1/trips', expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(input),
      })],
      ['/api/v1/trips/12'],
      ['/api/v1/trips/12', expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ name: 'Updated Tokyo' }),
      })],
      ['/api/v1/trips/12', expect.objectContaining({ method: 'DELETE' })],
    ])
  })

  it('rejects malformed successful responses before they reach the UI', async () => {
    const request = vi.fn().mockResolvedValue({ ...trip, owner_id: '7' })
    await expect(getTrip(request, '12')).rejects.toMatchObject({
      code: 'INVALID_RESPONSE',
    })
  })

  it('preserves API errors for callers to render safely', async () => {
    const error = new ApiError(404, 'TRIP_NOT_FOUND', 'Trip not found')
    const request = vi.fn().mockRejectedValue(error)
    await expect(getTrip(request, '12')).rejects.toBe(error)
  })
})
