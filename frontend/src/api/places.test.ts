import { describe, expect, it, vi } from 'vitest'
import {
  createPlace, deletePlace, getDayRoute, listPlaces, optimizeDay, searchPlaces, updatePlace,
} from './places'

const stamp = '2026-09-20T00:00:00Z'
const place = {
  id: 1, trip_id: 12, proposed_by_user_id: 7, name: 'Senso-ji', address: null, latitude: 35.714766,
  longitude: 139.796655, provider: 'nominatim', provider_place_id: 'N123', note: null,
  created_at: stamp, updated_at: stamp,
}
const route = {
  date: '2027-06-10',
  stops: [{ item_id: 9, place_id: 1, name: 'Senso-ji', latitude: 35.7, longitude: 139.8 }],
  legs: [], total_distance_km: 0, unlocated_item_ids: [10],
}

describe('place and route adapters', () => {
  it('uses the versioned place paths and JSON bodies', async () => {
    const request = vi.fn()
      .mockResolvedValueOnce([place]).mockResolvedValueOnce(place)
      .mockResolvedValueOnce({ ...place, name: 'Temple' }).mockResolvedValueOnce(undefined)
    await expect(listPlaces(request, '12')).resolves.toEqual([place])
    await expect(createPlace(request, '12', { name: 'Senso-ji', latitude: 35.7, longitude: 139.8 }))
      .resolves.toEqual(place)
    await expect(updatePlace(request, '12', 1, { name: 'Temple' })).resolves.toMatchObject({ name: 'Temple' })
    await expect(deletePlace(request, '12', 1)).resolves.toBeUndefined()
    expect(request.mock.calls.map(([path, init]) => [path, init?.method ?? 'GET'])).toEqual([
      ['/api/v1/trips/12/places', 'GET'], ['/api/v1/trips/12/places', 'POST'],
      ['/api/v1/trips/12/places/1', 'PATCH'], ['/api/v1/trips/12/places/1', 'DELETE'],
    ])
    expect(JSON.parse(request.mock.calls[2][1].body)).toEqual({ name: 'Temple' })
  })

  it('encodes the search query and validates results', async () => {
    const request = vi.fn().mockResolvedValue([{
      provider: 'nominatim', provider_place_id: 'N1', name: 'A & B', address: null, latitude: 1, longitude: 2,
    }])
    await expect(searchPlaces(request, 'A & B?')).resolves.toHaveLength(1)
    expect(request.mock.calls[0][0]).toBe('/api/v1/geocode?q=A+%26+B%3F&limit=5')
  })

  it('loads a route and posts an optimize preview', async () => {
    const plan = {
      date: route.date, keep_first: false, changed: false, original_item_ids: [9, 10],
      proposed_item_ids: [9, 10], anchored_item_ids: [10], original_route: route, proposed_route: route,
    }
    const request = vi.fn().mockResolvedValueOnce(route).mockResolvedValueOnce(plan)
    await expect(getDayRoute(request, '12', '2027-06-10')).resolves.toEqual(route)
    await expect(optimizeDay(request, '12', '2027-06-10', false)).resolves.toEqual(plan)
    expect(request.mock.calls[0][0]).toBe('/api/v1/trips/12/itinerary/route?date=2027-06-10')
    expect(request.mock.calls[1][0]).toBe('/api/v1/trips/12/itinerary/optimize')
    expect(JSON.parse(request.mock.calls[1][1].body)).toEqual({ date: '2027-06-10', keep_first: false })
  })

  it.each([
    { ...place, latitude: '35.7' }, { ...place, latitude: 91 }, { ...place, longitude: Number.NaN },
    { ...place, proposed_by_user_id: null }, { ...place, note: 3 }, [],
  ])('rejects a malformed place %#', async (body) => {
    await expect(listPlaces(vi.fn().mockResolvedValue([body]), '12'))
      .rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
  })

  it.each([
    { ...route, stops: 'none' }, { ...route, total_distance_km: '1' }, { ...route, unlocated_item_ids: ['10'] },
  ])('rejects a malformed route %#', async (body) => {
    await expect(getDayRoute(vi.fn().mockResolvedValue(body), '12', '2027-06-10'))
      .rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
  })
})
