import { ApiError } from './client'

/** One change notification from GET /api/v1/trips/{id}/events, plus the client's own `resync`. */
export type TripEvent = {
  type: string
  trip_id?: number
  entity?: 'trip' | 'itinerary' | 'expense' | 'place' | 'member'
  action?: 'created' | 'updated' | 'deleted' | 'reordered' | 'joined'
  actor_id?: number
  entity_id?: number
  version?: number
  date?: string
  occurred_at?: string
}

export type LiveStatus = 'connecting' | 'live' | 'reconnecting' | 'offline'
export type StreamRequest = (path: string, signal: AbortSignal) => Promise<Response>

export const RESYNC: TripEvent = { type: 'resync' }
// Reconnect delays in milliseconds; the last one repeats.
export const BACKOFF = [1000, 2000, 4000, 8000, 15000, 30000]

/** Parses one blank-line-terminated SSE block; comments and empty blocks yield null. */
export function parseSseBlock(block: string): { event: string; data: string } | null {
  let event = 'message'
  const data: string[] = []
  for (const line of block.split('\n')) {
    if (!line || line.startsWith(':')) continue
    const colon = line.indexOf(':')
    const field = colon === -1 ? line : line.slice(0, colon)
    const value = colon === -1 ? '' : line.slice(colon + 1).replace(/^ /, '')
    if (field === 'event') event = value
    else if (field === 'data') data.push(value)
  }
  return data.length === 0 ? null : { event, data: data.join('\n') }
}

/** Yields parsed events from a text/event-stream body until it ends, is cancelled, or `signal` aborts. */
export async function* readSse(
  body: ReadableStream<Uint8Array>, signal?: AbortSignal,
): AsyncGenerator<{ event: string; data: string }> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  const cancel = () => { void reader.cancel().catch(() => undefined) }
  signal?.addEventListener('abort', cancel, { once: true })
  let buffer = ''
  try {
    for (;;) {
      const { value, done } = await reader.read()
      buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, '\n')
      let end = buffer.indexOf('\n\n')
      while (end !== -1) {
        const parsed = parseSseBlock(buffer.slice(0, end))
        buffer = buffer.slice(end + 2)
        if (parsed) yield parsed
        end = buffer.indexOf('\n\n')
      }
      if (done) return
    }
  } finally {
    signal?.removeEventListener('abort', cancel)
    reader.releaseLock()
  }
}

function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const timer = setTimeout(finish, ms)
    function finish() {
      clearTimeout(timer)
      signal.removeEventListener('abort', finish)
      resolve()
    }
    signal.addEventListener('abort', finish, { once: true })
  })
}

function parseEvent(event: string, data: string): TripEvent {
  try {
    const body: unknown = JSON.parse(data)
    if (typeof body === 'object' && body !== null) return { ...(body as Omit<TripEvent, 'type'>), type: event }
  } catch { /* fall through: an unparseable body still names its event */ }
  return { type: event }
}

/**
 * Keeps one trip's event stream open until `signal` aborts. Every successful
 * (re)connection after the first emits a synthetic `resync`, because changes
 * made while disconnected were never delivered. Access errors stop for good;
 * anything else retries with backoff. Ends on `trip.deleted`.
 */
export async function subscribeTripEvents({ stream, tripId, onEvent, onStatus, signal, backoff = BACKOFF }: {
  stream: StreamRequest
  tripId: string
  onEvent: (event: TripEvent) => void
  onStatus: (status: LiveStatus) => void
  signal: AbortSignal
  backoff?: number[]
}): Promise<void> {
  const path = `/api/v1/trips/${encodeURIComponent(tripId)}/events`
  let attempt = 0
  let connected = false
  const report = (status: LiveStatus) => { if (!signal.aborted) onStatus(status) }
  report('connecting')
  while (!signal.aborted) {
    try {
      const response = await stream(path, signal)
      for await (const { event, data } of readSse(response.body!, signal)) {
        if (signal.aborted) return
        if (event === 'ready') {
          if (connected) onEvent(RESYNC)
          connected = true
          attempt = 0
          report('live')
          continue
        }
        const parsed = parseEvent(event, data)
        onEvent(parsed)
        if (parsed.type === 'trip.deleted') {
          report('offline')
          return
        }
      }
      // The server closed the stream (restart or deploy): reconnect.
    } catch (error) {
      if (signal.aborted) return
      if (error instanceof ApiError && [401, 403, 404].includes(error.status)) {
        report('offline')
        return
      }
    }
    // Say so at once; the wait below is the backoff before the next attempt.
    report(connected ? 'reconnecting' : 'connecting')
    await wait(backoff[Math.min(attempt, backoff.length - 1)], signal)
    attempt += 1
  }
}
