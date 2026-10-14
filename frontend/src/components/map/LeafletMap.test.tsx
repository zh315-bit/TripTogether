import { fireEvent, render, screen } from '@testing-library/react'
import L from 'leaflet'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  DEFAULT_TILE_URL, LeafletMap, OSM_ATTRIBUTION, resetTileConfigWarning, tileConfig,
} from './LeafletMap'
import type { MapMarker } from './LeafletMap'

const hostile = '<img src=x onerror="window.__xss = true">Temple'

const marker = (id: string, label: string, tooltip: string, position: [number, number] = [35.7, 139.8]): MapMarker => ({
  id, position, label, tooltip, color: '#1c6fc2', kind: 'place',
})

beforeEach(() => resetTileConfigWarning())

describe('LeafletMap (real Leaflet in jsdom)', () => {
  it('renders markers as text, never as HTML, with OSM attribution', () => {
    const { container } = render(<LeafletMap label="Trip map" lines={[]}
      markers={[marker('a', '<b>', hostile), marker('b', 'F', 'Tower', [35.6, 139.7])]} />)
    expect(screen.getByRole('region', { name: 'Trip map' })).toBeInTheDocument()
    const icons = container.querySelectorAll('.map-marker')
    expect(icons).toHaveLength(2)
    expect(icons[0].textContent).toBe('<b>')
    expect(icons[0].querySelector('b, img')).toBeNull()
    expect(icons[0].getAttribute('title')).toBe(hostile)
    expect((icons[0] as HTMLElement).style.getPropertyValue('--marker-color')).toBe('#1c6fc2')
    expect(container.querySelector('img[src="x"]')).toBeNull()
    expect((window as unknown as { __xss?: boolean }).__xss).toBeUndefined()
    const attribution = container.querySelector('.leaflet-control-attribution')
    expect(attribution).toHaveTextContent('© OpenStreetMap contributors')
    expect(attribution?.querySelector('a[href="https://www.openstreetmap.org/copyright"]')).not.toBeNull()
  })

  it('draws polylines and redraws without duplicating layers', () => {
    const lines = [{ id: 'route', color: '#17233a', positions: [[35.7, 139.7], [35.6, 139.8]] as [number, number][] }]
    const { container, rerender } = render(<LeafletMap label="Trip map" markers={[]} lines={lines} />)
    expect(container.querySelectorAll('path.leaflet-interactive')).toHaveLength(1)
    rerender(<LeafletMap label="Trip map" markers={[]} lines={[...lines, { ...lines[0], id: 'suggested', dashed: true }]} />)
    expect(container.querySelectorAll('path.leaflet-interactive')).toHaveLength(2)
    expect(container.querySelector('path[stroke-dasharray="8 8"]')).not.toBeNull()
    rerender(<LeafletMap label="Trip map" markers={[]} lines={[]} />)
    expect(container.querySelectorAll('path.leaflet-interactive')).toHaveLength(0)
  })

  it('reports clicks only while picking', () => {
    const onPick = vi.fn()
    const { rerender } = render(<LeafletMap label="Trip map" markers={[]} lines={[]} />)
    const host = screen.getByRole('region', { name: 'Trip map' })
    fireEvent.click(host)
    rerender(<LeafletMap label="Trip map" markers={[]} lines={[]} onPick={onPick} />)
    expect(host).toHaveClass('map-picking')
    fireEvent.click(host, { clientX: 10, clientY: 10 })
    expect(onPick).toHaveBeenCalledTimes(1)
    const [[lat, lng]] = onPick.mock.calls[0]
    expect(Number.isFinite(lat) && Number.isFinite(lng) && Math.abs(lng) <= 180).toBe(true)
    rerender(<LeafletMap label="Trip map" markers={[]} lines={[]} />)
    expect(host).not.toHaveClass('map-picking')
    fireEvent.click(host)
    expect(onPick).toHaveBeenCalledTimes(1)
  })

  it('calls invalidateSize when the container resizes and disconnects on unmount', () => {
    const observers: { callback: ResizeObserverCallback; observe: ReturnType<typeof vi.fn>; disconnect: ReturnType<typeof vi.fn> }[] = []
    vi.stubGlobal('ResizeObserver', class {
      observe = vi.fn()
      disconnect = vi.fn()
      unobserve = vi.fn()
      callback: ResizeObserverCallback
      constructor(callback: ResizeObserverCallback) {
        this.callback = callback
        observers.push(this)
      }
    })
    const invalidate = vi.spyOn(L.Map.prototype, 'invalidateSize')
    const { unmount } = render(<LeafletMap label="Trip map" markers={[]} lines={[]} />)
    const [observer] = observers
    expect(observer.observe).toHaveBeenCalledWith(screen.getByRole('region', { name: 'Trip map' }))
    invalidate.mockClear()
    observer.callback([], observer as unknown as ResizeObserver)
    expect(invalidate).toHaveBeenCalledTimes(1)
    unmount()
    expect(observer.disconnect).toHaveBeenCalledTimes(1)
  })
})

describe('tile configuration', () => {
  const custom = 'https://tiles.example.com/{z}/{x}/{y}.png'

  it('defaults to OpenStreetMap tiles and credit', () => {
    expect(tileConfig()).toEqual({ url: DEFAULT_TILE_URL, attribution: OSM_ATTRIBUTION })
  })

  it('uses a custom provider only together with its own credit, escaped as text', () => {
    vi.stubEnv('VITE_MAP_TILE_URL', custom)
    vi.stubEnv('VITE_MAP_TILE_ATTRIBUTION', ' © Example Maps <b onmouseover="x">& Co</b> ')
    expect(tileConfig()).toEqual({
      url: custom,
      attribution: '© Example Maps &lt;b onmouseover=&quot;x&quot;&gt;&amp; Co&lt;/b&gt;',
    })
  })

  it.each([
    [custom, undefined, /without VITE_MAP_TILE_ATTRIBUTION/],
    [custom, '   ', /without VITE_MAP_TILE_ATTRIBUTION/],
    ['http://tiles.example.com/{z}/{x}/{y}.png', 'Example', /must be an HTTPS template/],
    ['https://tiles.example.com/tile.png', 'Example', /must be an HTTPS template/],
  ])('falls back to OSM for url=%s attribution=%s and warns once', (url, attribution, warning) => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    vi.stubEnv('VITE_MAP_TILE_URL', url)
    if (attribution !== undefined) vi.stubEnv('VITE_MAP_TILE_ATTRIBUTION', attribution)
    expect(tileConfig()).toEqual({ url: DEFAULT_TILE_URL, attribution: OSM_ATTRIBUTION })
    expect(tileConfig()).toEqual({ url: DEFAULT_TILE_URL, attribution: OSM_ATTRIBUTION })
    expect(warn).toHaveBeenCalledTimes(1)
    expect(warn.mock.calls[0][0]).toMatch(warning)
  })

  it('ignores an attribution without a custom URL', () => {
    vi.stubEnv('VITE_MAP_TILE_ATTRIBUTION', 'Example')
    expect(tileConfig()).toEqual({ url: DEFAULT_TILE_URL, attribution: OSM_ATTRIBUTION })
  })

  it('renders a custom credit as text in the attribution control', () => {
    vi.stubEnv('VITE_MAP_TILE_URL', custom)
    vi.stubEnv('VITE_MAP_TILE_ATTRIBUTION', '<img src=y onerror="window.__credit = 1">Example Maps')
    const tileLayer = vi.spyOn(L, 'tileLayer')
    const { container } = render(<LeafletMap label="Trip map" markers={[]} lines={[]} />)
    expect(tileLayer).toHaveBeenCalledWith(custom, expect.objectContaining({ maxZoom: 19 }))
    const control = container.querySelector('.leaflet-control-attribution')
    expect(control).toHaveTextContent('<img src=y onerror="window.__credit = 1">Example Maps')
    expect(control?.querySelector('img')).toBeNull()
    expect((window as unknown as { __credit?: number }).__credit).toBeUndefined()
  })
})
