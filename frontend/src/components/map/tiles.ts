// Tile source and credit for the map; kept out of LeafletMap.tsx so that file
// exports only its component (React Fast Refresh requirement).
export const DEFAULT_TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
// Static markup, never user data, so it is safe as Leaflet attribution HTML.
export const OSM_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'

export type TileConfig = { url: string; attribution: string }

const OSM_TILES: TileConfig = { url: DEFAULT_TILE_URL, attribution: OSM_ATTRIBUTION }
let warned = false

function warnOnce(message: string) {
  if (warned) return
  warned = true
  console.warn(message)
}

/** Test hook: the fallback warning is otherwise logged once per page load. */
export function resetTileConfigWarning() {
  warned = false
}

export function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (char) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char] ?? char
  ))
}

/**
 * Tiles and their credit travel together: a custom VITE_MAP_TILE_URL needs a
 * VITE_MAP_TILE_ATTRIBUTION, otherwise the map falls back to OSM tiles with
 * the OSM credit so it is never shown uncredited. The custom credit is plain
 * text; Leaflet renders attribution as HTML, so it is escaped first.
 */
export function tileConfig(): TileConfig {
  const url = import.meta.env.VITE_MAP_TILE_URL?.trim()
  const attribution = import.meta.env.VITE_MAP_TILE_ATTRIBUTION?.trim()
  if (!url) return OSM_TILES
  if (!url.startsWith('https://') || !['{z}', '{x}', '{y}'].every((part) => url.includes(part))) {
    warnOnce('VITE_MAP_TILE_URL must be an HTTPS template with {z}, {x} and {y}; using OpenStreetMap tiles.')
    return OSM_TILES
  }
  if (!attribution) {
    warnOnce('VITE_MAP_TILE_URL is set without VITE_MAP_TILE_ATTRIBUTION; using OpenStreetMap tiles.')
    return OSM_TILES
  }
  return { url, attribution: escapeHtml(attribution) }
}
