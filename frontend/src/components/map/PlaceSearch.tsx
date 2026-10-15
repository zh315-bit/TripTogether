import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError } from '../../api/client'
import { searchPlaces } from '../../api/places'
import { useAuth } from '../../auth/AuthContext'
import type { GeocodeResult } from '../../types/places'
import { errorText } from './errorText'

type Props = {
  /** Saves a result to the pool; resolves to a user-facing status line. */
  onAdd: (result: GeocodeResult) => Promise<string>
}

const DISABLED_MESSAGE =
  'Place search is turned off. Add places manually below: pick a point on the map or enter coordinates.'

/**
 * Search runs only on submit (button or Enter). There is deliberately no
 * autocomplete or debounce: the public Nominatim policy forbids per-keystroke
 * queries, and the backend shares one request per second across all users.
 */
export function PlaceSearch({ onAdd }: Props) {
  const { request } = useAuth()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<GeocodeResult[] | null>(null)
  const [pending, setPending] = useState(false)
  const [cooldown, setCooldown] = useState(0)
  const [message, setMessage] = useState('')
  const [adding, setAdding] = useState<string | null>(null)

  useEffect(() => {
    if (cooldown <= 0) return
    const timer = window.setTimeout(() => setCooldown((value) => value - 1), 1000)
    return () => window.clearTimeout(timer)
  }, [cooldown])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmed = query.trim()
    if (pending || cooldown > 0) return
    if (trimmed.length < 2) {
      setMessage('Enter at least two characters to search.')
      return
    }
    setPending(true)
    setMessage('')
    try {
      const found = await searchPlaces(request, trimmed)
      setResults(found)
      if (found.length === 0) setMessage('No places found. Try another name or add the place manually.')
    } catch (error) {
      setResults(null)
      if (error instanceof ApiError && error.code === 'GEOCODER_BUSY') {
        setCooldown(Math.max(1, error.retryAfter ?? 1))
        setMessage('Place search is busy for everyone right now. You can search again shortly.')
      } else if (error instanceof ApiError && error.code === 'GEOCODER_DISABLED') {
        setMessage(DISABLED_MESSAGE)
      } else if (error instanceof ApiError && error.code === 'GEOCODER_UNAVAILABLE') {
        setMessage('Place search is temporarily unavailable. Try again later or add the place manually.')
      } else {
        setMessage(errorText(error, 'Could not search for places.'))
      }
    } finally {
      setPending(false)
    }
  }

  async function add(result: GeocodeResult) {
    setAdding(result.provider_place_id)
    try {
      setMessage(await onAdd(result))
    } finally {
      setAdding(null)
    }
  }

  const label = pending ? 'Searching...' : cooldown > 0 ? `Retry in ${cooldown}s` : 'Search'
  return <section className="map-card" aria-labelledby="place-search-title">
    <h3 id="place-search-title">Search places</h3>
    <form className="inline-form" role="search" onSubmit={submit}>
      <label className="visually-hidden" htmlFor="place-search-query">Place name or address</label>
      <input id="place-search-query" value={query} placeholder="e.g. Senso-ji, Tokyo"
        maxLength={200} onChange={(event) => setQuery(event.target.value)} />
      <button className="primary-button" type="submit" disabled={pending || cooldown > 0}>{label}</button>
    </form>
    {message && <p className="map-status" role="status">{message}</p>}
    {results && results.length > 0 && <ul className="map-result-list" aria-label="Search results">
      {results.map((result) => <li key={result.provider_place_id}>
        <div><strong>{result.name}</strong>{result.address && <span className="trip-meta">{result.address}</span>}</div>
        <button className="retry-button" type="button" disabled={adding !== null}
          aria-label={`Add ${result.name} to the place pool`} onClick={() => void add(result)}>
          {adding === result.provider_place_id ? 'Adding...' : 'Add'}
        </button>
      </li>)}
    </ul>}
    <p className="map-attribution">Search data &copy; <a href="https://www.openstreetmap.org/copyright"
      target="_blank" rel="noreferrer">OpenStreetMap</a> contributors, via Nominatim.</p>
  </section>
}
