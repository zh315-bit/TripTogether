import { useEffect, useMemo, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { tileConfig } from './tiles'

export type LatLng = [number, number]

export type MapMarker = {
  id: string
  position: LatLng
  /** One or two characters drawn inside the marker (member initial or stop number). */
  label: string
  color: string
  tooltip: string
  kind: 'place' | 'stop'
  /** The pool place this marker stands for; clicking it selects that place. */
  placeId?: number
}

export type MapLine = { id: string; positions: LatLng[]; color: string; dashed?: boolean }

type Props = {
  markers: MapMarker[]
  lines: MapLine[]
  /** When set, a click on the map reports its coordinates instead of panning only. */
  onPick?: (position: LatLng) => void
  label: string
  selectedPlaceId?: number | null
  hoveredPlaceId?: number | null
  /** A marker click selects its place; a click on empty map clears it (null). */
  onSelectPlace?: (placeId: number | null) => void
  onHoverPlace?: (placeId: number | null) => void
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
export function LeafletMap({
  markers, lines, onPick, label, selectedPlaceId = null, hoveredPlaceId = null, onSelectPlace, onHoverPlace,
}: Props) {
  const container = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const layers = useRef<L.LayerGroup | null>(null)
  const drawn = useRef<{ marker: L.Marker; placeId?: number }[]>([])
  // Handlers are read through a ref so new callback identities do not redraw every marker.
  const handlers = useRef({ onSelectPlace, onHoverPlace })
  useEffect(() => {
    handlers.current = { onSelectPlace, onHoverPlace }
  }, [onSelectPlace, onHoverPlace])

  useEffect(() => {
    const element = container.current
    if (!element) return
    const instance = L.map(element, { center: [20, 0], zoom: 2, worldCopyJump: true })
    const tiles = tileConfig()
    L.tileLayer(tiles.url, { attribution: tiles.attribution, maxZoom: 19 }).addTo(instance)
    layers.current = L.layerGroup().addTo(instance)
    map.current = instance
    // Leaflet measures its container once; layout changes (sidebar wrap, rotation,
    // breakpoints) would otherwise leave grey, unloaded tile areas.
    const observer = typeof ResizeObserver === 'undefined'
      ? null : new ResizeObserver(() => instance.invalidateSize())
    observer?.observe(element)
    return () => {
      observer?.disconnect()
      instance.remove()
      map.current = null
      layers.current = null
    }
  }, [])

  useEffect(() => {
    const group = layers.current
    if (!group) return
    group.clearLayers()
    drawn.current = []
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
      const instance = L.marker(marker.position, { icon, title: marker.tooltip, alt: marker.tooltip, keyboard: true })
        .bindTooltip(textElement('span', '', marker.tooltip))
        .addTo(group)
      instance.getElement()?.style.setProperty('--marker-color', marker.color)
      const { placeId } = marker
      if (placeId !== undefined) {
        // Leaflet also fires click for Enter on a focused marker, so this covers the keyboard.
        instance.on('click', () => handlers.current.onSelectPlace?.(placeId))
        instance.on('mouseover', () => handlers.current.onHoverPlace?.(placeId))
        instance.on('mouseout', () => handlers.current.onHoverPlace?.(null))
      }
      drawn.current.push({ marker: instance, placeId })
    }
  }, [markers, lines])

  // Highlighting only toggles classes, so hovering a list row never rebuilds the layers.
  useEffect(() => {
    for (const { marker, placeId } of drawn.current) {
      const selected = placeId !== undefined && placeId === selectedPlaceId
      const element = marker.getElement()
      element?.classList.toggle('is-selected', selected)
      element?.classList.toggle('is-hovered', placeId !== undefined && placeId === hoveredPlaceId)
      marker.setZIndexOffset(selected ? 1000 : 0)
    }
  }, [markers, lines, selectedPlaceId, hoveredPlaceId])

  // Bring a newly selected place into view, clear of the detail card at the bottom.
  useEffect(() => {
    const instance = map.current
    const target = drawn.current.find(({ placeId }) => placeId === selectedPlaceId)
    if (!instance || !target) return
    const position = target.marker.getLatLng()
    if (instance.getZoom() < 12) instance.setView(position, 14, { animate: false })
    // The card plus the phone's peeking sheet cover ~360px; keep the marker clear above them.
    const bottom = Math.min(440, instance.getSize().y * 0.65)
    instance.panInside(position, { paddingTopLeft: [48, 64], paddingBottomRight: [48, bottom] })
    // Only on a new selection, not when markers redraw.
  }, [selectedPlaceId])

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
    if (!instance || !element) return
    if (!onPick) {
      const clear = () => handlers.current.onSelectPlace?.(null)
      instance.on('click', clear)
      return () => {
        instance.off('click', clear)
      }
    }
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
