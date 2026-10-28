import { describe, expect, it, vi } from 'vitest'
import { ApiError } from './client'
import { RESYNC, parseSseBlock, readSse, subscribeTripEvents } from './events'
import type { LiveStatus, TripEvent } from './events'

const encoder = new TextEncoder()

function chunked(chunks: string[]): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.close()
    },
  })
}

async function collect<T>(source: AsyncGenerator<T>): Promise<T[]> {
  const result: T[] = []
  for await (const value of source) result.push(value)
  return result
}

/** A stream the test feeds by hand, like the server would. */
function openStream() {
  let controller!: ReadableStreamDefaultController<Uint8Array>
  const response = new Response(new ReadableStream<Uint8Array>({ start(c) { controller = c } }), {
    headers: { 'Content-Type': 'text/event-stream' },
  })
  return {
    response,
    send: (event: string, data: object) => controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)),
    close: () => controller.close(),
  }
}

describe('SSE parsing', () => {
  it('parses event and multi-line data fields, ignoring comments', () => {
    expect(parseSseBlock('event: itinerary.updated\ndata: {"a":1}')).toEqual({ event: 'itinerary.updated', data: '{"a":1}' })
    expect(parseSseBlock('data: one\ndata: two')).toEqual({ event: 'message', data: 'one\ntwo' })
    expect(parseSseBlock(': keep-alive')).toBeNull()
    expect(parseSseBlock('event: ready')).toBeNull()
  })

  it('reads events split across chunks, with CRLF line endings and heartbeats', async () => {
    const events = await collect(readSse(chunked([
      'event: ready\ndata: {"trip_id":1}\n\n: keep-al', 'ive\n\nevent: place.cre',
      'ated\r\ndata: {"entity_id":4}\r\n\r\n',
    ])))
    expect(events).toEqual([
      { event: 'ready', data: '{"trip_id":1}' }, { event: 'place.created', data: '{"entity_id":4}' },
    ])
  })
})

describe('subscribeTripEvents', () => {
  function harness() {
    const streams: ReturnType<typeof openStream>[] = []
    const stream = vi.fn(async () => {
      const next = openStream()
      streams.push(next)
      return next.response
    })
    const events: TripEvent[] = []
    const statuses: LiveStatus[] = []
    const controller = new AbortController()
    const done = subscribeTripEvents({
      stream, tripId: '12', signal: controller.signal, backoff: [0],
      onEvent: (event) => events.push(event), onStatus: (status) => statuses.push(status),
    })
    return { stream, streams, events, statuses, controller, done }
  }

  it('relays events, resyncs after a reconnect and ends when the trip is deleted', async () => {
    const { stream, streams, events, statuses, done } = harness()
    await vi.waitFor(() => expect(streams).toHaveLength(1))
    expect(stream).toHaveBeenCalledWith('/api/v1/trips/12/events', expect.any(AbortSignal))
    streams[0].send('ready', { trip_id: 12, user_id: 7 })
    streams[0].send('itinerary.updated', { trip_id: 12, entity: 'itinerary', action: 'updated', actor_id: 8, entity_id: 5, version: 3 })
    await vi.waitFor(() => expect(events).toHaveLength(1))
    expect(events[0]).toEqual({ type: 'itinerary.updated', trip_id: 12, entity: 'itinerary', action: 'updated', actor_id: 8, entity_id: 5, version: 3 })
    expect(statuses).toEqual(['connecting', 'live'])
    // The server closes the stream (deploy): reconnect, and the fresh `ready` asks for a resync.
    streams[0].close()
    await vi.waitFor(() => expect(streams).toHaveLength(2))
    streams[1].send('ready', { trip_id: 12, user_id: 7 })
    await vi.waitFor(() => expect(events).toHaveLength(2))
    expect(events[1]).toBe(RESYNC)
    expect(statuses).toEqual(['connecting', 'live', 'reconnecting', 'live'])
    streams[1].send('trip.deleted', { trip_id: 12, entity: 'trip', action: 'deleted', actor_id: 7, entity_id: 12 })
    await done
    expect(events[2].type).toBe('trip.deleted')
    expect(statuses.at(-1)).toBe('offline')
    expect(stream).toHaveBeenCalledTimes(2)
  })

  it('stops for good when access is refused, and retries other failures', async () => {
    const stream = vi.fn()
      .mockRejectedValueOnce(new ApiError(0, 'NETWORK_ERROR', 'down'))
      .mockRejectedValueOnce(new ApiError(404, 'TRIP_NOT_FOUND', 'Trip not found'))
    const statuses: LiveStatus[] = []
    await subscribeTripEvents({
      stream, tripId: '12', signal: new AbortController().signal, backoff: [0],
      onEvent: () => undefined, onStatus: (status) => statuses.push(status),
    })
    expect(stream).toHaveBeenCalledTimes(2)
    expect(statuses).toEqual(['connecting', 'connecting', 'offline'])
  })

  it('aborting closes the stream and reports nothing further', async () => {
    const { streams, statuses, controller, done } = harness()
    await vi.waitFor(() => expect(streams).toHaveLength(1))
    streams[0].send('ready', {})
    await vi.waitFor(() => expect(statuses).toEqual(['connecting', 'live']))
    controller.abort()
    await done
    expect(statuses).toEqual(['connecting', 'live'])
  })
})
