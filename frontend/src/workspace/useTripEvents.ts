import { useEffect, useRef, useState } from 'react'
import { subscribeTripEvents } from '../api/events'
import type { LiveStatus, TripEvent } from '../api/events'
import { useAuth } from '../auth/AuthContext'

/** Subscribes to a trip's change stream for as long as the component is mounted. */
export function useTripEvents(tripId: string, onEvent: (event: TripEvent) => void): LiveStatus {
  const { stream } = useAuth()
  const [status, setStatus] = useState<LiveStatus>('connecting')
  // The latest handler sees current state without resubscribing on every render.
  const handler = useRef(onEvent)
  useEffect(() => { handler.current = onEvent })

  useEffect(() => {
    const controller = new AbortController()
    void subscribeTripEvents({
      stream, tripId, signal: controller.signal, onStatus: setStatus,
      onEvent: (event) => handler.current(event),
    })
    return () => controller.abort()
  }, [stream, tripId])

  return status
}
