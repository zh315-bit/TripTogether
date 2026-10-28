import { useCallback, useMemo, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { BalancePanel } from '../components/BalancePanel'
import { ExpensePanel } from '../components/ExpensePanel'
import { FinanceSummary } from '../components/FinanceSummary'
import { ItineraryPanel } from '../components/ItineraryPanel'
import { MembersPanel } from '../components/MembersPanel'
import { DayRoutePanel } from '../components/map/DayRoutePanel'
import { tripDays } from '../components/map/days'
import { km } from '../components/map/distance'
import { LeafletMap } from '../components/map/LeafletMap'
import type { LatLng } from '../components/map/LeafletMap'
import { PlaceDetailCard } from '../components/map/PlaceDetailCard'
import { PlacePool } from '../components/map/PlacePool'
import { PlaceSearch } from '../components/map/PlaceSearch'
import { useTripMap } from '../components/map/useTripMap'
import type { Trip } from '../types/trip'
import { memberStyle } from '../utils/memberColors'
import { Icon } from './Icon'
import type { IconName } from './Icon'
import { TripSettings } from './TripSettings'
import '../components/map/MapPanel.css'
import './TripWorkspace.css'

const PANELS = [
  { id: 'places', label: 'Places', icon: 'pin' },
  { id: 'itinerary', label: 'Itinerary', icon: 'calendar' },
  { id: 'expenses', label: 'Expenses', icon: 'receipt' },
  { id: 'balances', label: 'Balances', icon: 'scale' },
  { id: 'members', label: 'Members', icon: 'users' },
  { id: 'settings', label: 'Trip details', icon: 'sliders' },
] as const satisfies readonly { id: string; label: string; icon: IconName }[]
type PanelId = (typeof PANELS)[number]['id']
type Sheet = 'peek' | 'half' | 'full'

const isPanel = (value: string | null): value is PanelId => PANELS.some((panel) => panel.id === value)

type Props = {
  trip: Trip
  owner: boolean
  onTripUpdated: (trip: Trip) => void
  onTripDeleted: (tripId: number) => void
}

/**
 * The signed-in home: the map fills the screen and every feature lives in the
 * sidebar (a bottom sheet on phones). All panels share one useTripMap state, so
 * edits anywhere redraw the map.
 */
export default function TripWorkspace({ trip, owner, onTripUpdated, onTripDeleted }: Props) {
  const map = useTripMap(trip)
  const [params, setParams] = useSearchParams()
  const requested = params.get('panel')
  const panel: PanelId = isPanel(requested) ? requested : 'places'
  const [sheet, setSheet] = useState<Sheet>('peek')
  const [balanceKey, setBalanceKey] = useState(0)
  const tabs = useRef<(HTMLButtonElement | null)[]>([])
  const { selectPlace } = map
  // On phones the sheet drops to its peek height so the map and the detail card show.
  const showPlace = useCallback((placeId: number | null) => {
    selectPlace(placeId)
    if (placeId !== null) setSheet('peek')
  }, [selectPlace])
  const closeDetail = useCallback(() => selectPlace(null), [selectPlace])
  // The map frames the route day's stops; "Show all places" lasts until the day changes.
  const [showAllFor, setShowAllFor] = useState<string | null>(null)
  const stops = map.route?.stops ?? []
  const dayStops = useMemo<LatLng[]>(
    () => (map.route?.stops ?? []).map((stop) => [stop.latitude, stop.longitude]), [map.route])
  const framingDay = stops.length > 0 && showAllFor !== map.route?.date
  const days = useMemo(() => tripDays(trip.start_date, trip.end_date), [trip.start_date, trip.end_date])
  const scheduledPlaceIds = useMemo(() => new Set(map.items
    .filter((item) => item.date === map.day && item.place_id !== null).map((item) => item.place_id!)), [map.items, map.day])

  function choose(next: PanelId) {
    setParams((current) => {
      const updated = new URLSearchParams(current)
      updated.set('panel', next)
      return updated
    }, { replace: true })
    // On phones, opening a section lifts the sheet so its content is visible.
    if (sheet === 'peek') setSheet('half')
  }

  function onTabKey(event: KeyboardEvent<HTMLDivElement>) {
    const keys = ['ArrowDown', 'ArrowUp', 'ArrowRight', 'ArrowLeft', 'Home', 'End']
    if (!keys.includes(event.key)) return
    event.preventDefault()
    const index = PANELS.findIndex((item) => item.id === panel)
    const last = PANELS.length - 1
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? last
      : event.key === 'ArrowDown' || event.key === 'ArrowRight' ? (index + 1) % PANELS.length
        : (index - 1 + PANELS.length) % PANELS.length
    choose(PANELS[next].id)
    tabs.current[next]?.focus()
  }

  const nextSheet: Record<Sheet, Sheet> = { peek: 'half', half: 'full', full: 'peek' }
  const sheetLabel: Record<Sheet, string> = { peek: 'Show panel', half: 'Expand panel', full: 'Collapse panel' }

  return <div className="trip-workspace">
    <aside className={`workspace-sidebar sheet-${sheet}`} aria-label="Trip tools">
      <button className="sheet-handle" type="button" aria-expanded={sheet !== 'peek'}
        aria-label={sheetLabel[sheet]} onClick={() => setSheet(nextSheet[sheet])}><span aria-hidden="true" /></button>
      <div className="panel-tabs" role="tablist" aria-label="Trip tools" onKeyDown={onTabKey}>
        {PANELS.map((item, index) => <button key={item.id} ref={(node) => { tabs.current[index] = node }}
          id={`panel-tab-${item.id}`} type="button" role="tab" aria-selected={panel === item.id}
          aria-controls="workspace-panel" tabIndex={panel === item.id ? 0 : -1}
          className={panel === item.id ? 'active' : ''} onClick={() => choose(item.id)}>
          <Icon name={item.icon} /><span>{item.label}</span>
        </button>)}
      </div>
      {/* key: each panel opens scrolled to the top, not where the previous one was. */}
      <section key={panel} id="workspace-panel" className="panel-body" role="tabpanel" aria-labelledby={`panel-tab-${panel}`}>
        {map.status === 'loading' && <p role="status">Loading trip data...</p>}
        {map.status === 'error' && <div className="inline-error" role="alert"><p>{map.loadMessage}</p>
          <button className="retry-button" type="button" onClick={() => void map.load()}>Try again</button></div>}
        {map.status === 'ready' && <>
          {panel === 'places' && <>
            {map.notice && <p className="success-message" role="status">{map.notice}</p>}
            <PlaceSearch onAdd={map.addResult} />
            <PlacePool places={map.places} styles={map.styles} picking={map.picking} picked={map.picked}
              onTogglePicking={map.togglePicking} selectedPlaceId={map.selectedPlace?.id ?? null}
              hoveredPlaceId={map.hoveredPlaceId} onSelect={showPlace} onHover={map.hoverPlace}
              days={days} day={map.day} onDay={map.setDay} onAddToDay={map.addToDay}
              scheduledPlaceIds={scheduledPlaceIds}
              onCreate={map.createManual} onUpdate={map.update} onDelete={map.remove} />
          </>}
          {panel === 'itinerary' && <>
            <DayRoutePanel days={days} day={map.day} onDay={map.setDay}
              route={map.route} plan={map.plan} itemsById={map.itemsById} keepFirst={map.keepFirst}
              onKeepFirst={map.setKeepFirst} pending={map.pending} message={map.routeMessage}
              onSuggest={() => void map.suggest()} onApply={() => void map.apply()} onCancel={map.cancelPlan} />
            <ItineraryPanel trip={trip} places={map.places} refreshKey={map.itineraryVersion}
              onChanged={() => void map.refreshItinerary()} selectedPlaceId={map.selectedPlace?.id ?? null}
              route={map.route} onShowDay={map.setDay}
              onSelectPlace={showPlace} onHoverPlace={map.hoverPlace} />
          </>}
          {panel === 'expenses' && <>
            <FinanceSummary tripId={String(trip.id)} refreshKey={balanceKey} onOpenBalances={() => choose('balances')} />
            <ExpensePanel tripId={String(trip.id)} onChanged={() => setBalanceKey((key) => key + 1)} />
          </>}
          {panel === 'balances' && <BalancePanel tripId={String(trip.id)} refreshKey={balanceKey} />}
          {panel === 'members' && <MembersPanel tripId={String(trip.id)} owner={owner} />}
          {panel === 'settings' && <TripSettings trip={trip} owner={owner}
            onUpdated={onTripUpdated} onDeleted={onTripDeleted} />}
        </>}
      </section>
    </aside>
    <div className="workspace-map">
      <LeafletMap markers={map.markers} lines={map.lines} onPick={map.picking ? map.pick : undefined}
        label="Trip map with proposed places and the selected day's route"
        selectedPlaceId={map.selectedPlace?.id ?? null} hoveredPlaceId={map.hoveredPlaceId}
        onSelectPlace={showPlace} onHoverPlace={map.hoverPlace} fitTo={framingDay ? dayStops : undefined} />
      <div className="map-overlay map-overlay-top">
        {map.route && stops.length > 0 && <div className="map-chip-row">
          <p className="map-chip">{map.route.date} · {stops.length} stop{stops.length === 1 ? '' : 's'} ·{' '}
            {km(map.route.total_distance_km)} straight-line</p>
          <button className="map-chip map-chip-button" type="button"
            onClick={() => setShowAllFor(framingDay ? map.route!.date : null)}>
            {framingDay ? 'Show all places' : 'Focus on this day'}</button>
        </div>}
        {map.picking && <p className="map-chip map-chip-accent" role="status">Click the map to set the new place's coordinates.</p>}
      </div>
      {map.selectedPlace && <PlaceDetailCard place={map.selectedPlace} items={map.selectedItems}
        style={memberStyle(map.styles, map.selectedPlace.proposed_by_user_id)}
        onClose={closeDetail} onShowInList={() => choose('places')} />}
      {map.members.length > 0 && !map.selectedPlace && <ul className="member-legend map-overlay map-overlay-bottom" aria-label="Member colours">
        {map.members.map((member) => {
          const style = memberStyle(map.styles, member.user_id)
          return <li key={member.user_id}><span className="member-swatch" style={{ background: style.color }}
            aria-hidden="true">{style.initial}</span>{member.username}</li>
        })}
      </ul>}
    </div>
  </div>
}
