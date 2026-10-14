import { useEffect, useMemo, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

export const DEFAULT_TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
// Static markup, never user data, so it is safe as Leaflet attribution HTML.
export const OSM_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'

export type LatLng = [number, number]

export type MapMarker = {
  id: string
  position: LatLng
  /** One or two characters drawn inside the marker (member initial or stop number). */
  label: string
  color: string
  tooltip: string
  kind: 'place' | 'stop'
}

export type MapLine = { id: string; positions: LatLng[]; color: string; dashed?: boolean }

type Props = {
  markers: MapMarker[]
  lines: MapLine[]
  /** When set, a click on the map reports its coordinates instead of panning only. */
  onPick?: (position: LatLng) => void
  label: string
}

export function tileUrl(): string {
  const value = import.meta.env.VITE_MAP_TILE_URL?.trim()
  // Only HTTPS templates with all placeholders; anything else uses the default.
  if (value && value.startsWith('https://') && ['{z}', '{x}', '{y}'].every((part) => value.includes(part))) {
    return value
  }
  return DEFAULT_TILE_URL
}

function textElement(tag: string, className: string, value: string): HTMLElement {
  // textContent, never innerHTML: names come from other trip members.
  const element = document.createElement(tag)
  element.className = className
  element.textContent = value
  return element
}

/**
 * Thin imperative bridge: React owns the props, Leaflet owns the map DOM.
 * The map is created once; marker and line layers are redrawn when props change.
 */
export function LeafletMap({ markers, lines, onPick, label }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const layers = useRef<L.LayerGroup | null>(null)

  useEffect(() => {
    if (!container.current) return
    const instance = L.map(container.current, { center: [20, 0], zoom: 2, worldCopyJump: true })
    L.tileLayer(tileUrl(), { attribution: OSM_ATTRIBUTION, maxZoom: 19 }).addTo(instance)
    layers.current = L.layerGroup().addTo(instance)
    map.current = instance
    return () => {
      instance.remove()
      map.current = null
      layers.current = null
    }
  }, [])

  useEffect(() => {
    const group = layers.current
    if (!group) return
    group.clearLayers()
    for (const line of lines) {
      if (line.positions.length < 2) continue
      L.polyline(line.positions, {
        color: line.color, weight: 4, opacity: 0.85, dashArray: line.dashed ? '8 8' : undefined,
      }).addTo(group)
    }
    for (const marker of markers) {
      const icon = L.divIcon({
        className: `map-marker map-marker-${marker.kind}`,
        html: textElement('span', 'map-marker-label', marker.label),
        iconSize: marker.kind === 'stop' ? [22, 22] : [30, 30],
        // Stop numbers sit up and to the right so they do not hide the place marker.
        iconAnchor: marker.kind === 'stop' ? [-4, 26] : [15, 15],
      })
      L.marker(marker.position, { icon, title: marker.tooltip, alt: marker.tooltip, keyboard: true })
        .bindTooltip(textElement('span', '', marker.tooltip))
        .addTo(group)
        .getElement()?.style.setProperty('--marker-color', marker.color)
    }
  }, [markers, lines])

  // Refit only when the set of positions changes, so redraws keep the user's view.
  const boundsKey = useMemo(() => JSON.stringify([
    ...markers.map((marker) => marker.position), ...lines.flatMap((line) => line.positions),
  ]), [markers, lines])
  useEffect(() => {
    const instance = map.current
    if (!instance) return
    const positions = JSON.parse(boundsKey) as LatLng[]
    if (positions.length === 0) instance.setView([20, 0], 2)
    else if (positions.length === 1) instance.setView(positions[0], 14)
    else instance.fitBounds(L.latLngBounds(positions), { padding: [32, 32], maxZoom: 16 })
  }, [boundsKey])

  useEffect(() => {
    const instance = map.current
    const element = container.current
    if (!instance || !element || !onPick) return
    const handler = (event: L.LeafletMouseEvent) => onPick([event.latlng.lat, event.latlng.wrap().lng])
    instance.on('click', handler)
    element.classList.add('map-picking')
    return () => {
      instance.off('click', handler)
      element.classList.remove('map-picking')
    }
  }, [onPick])

  return <div ref={container} className="leaflet-host" role="region" aria-label={label} />
}
