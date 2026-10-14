import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { DEFAULT_TILE_URL, LeafletMap, tileUrl } from './LeafletMap'
import type { MapMarker } from './LeafletMap'

const hostile = '<img src=x onerror="window.__xss = true">Temple'

const marker = (id: string, label: string, tooltip: string, position: [number, number] = [35.7, 139.8]): MapMarker => ({
  id, position, label, tooltip, color: '#1c6fc2', kind: 'place',
})

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

  it.each([
    [undefined, DEFAULT_TILE_URL],
    ['https://tiles.example.com/{z}/{x}/{y}.png', 'https://tiles.example.com/{z}/{x}/{y}.png'],
    ['http://tiles.example.com/{z}/{x}/{y}.png', DEFAULT_TILE_URL],
    ['https://tiles.example.com/tile.png', DEFAULT_TILE_URL],
  ])('reads VITE_MAP_TILE_URL=%s safely', (value, expected) => {
    if (value !== undefined) vi.stubEnv('VITE_MAP_TILE_URL', value)
    expect(tileUrl()).toBe(expected)
  })
})
