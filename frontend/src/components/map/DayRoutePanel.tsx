import type { ItineraryItem } from '../../types/collaboration'
import type { DayRoute, OptimizePlan } from '../../types/places'

type Props = {
  days: string[]
  day: string
  onDay: (day: string) => void
  route: DayRoute | null
  plan: OptimizePlan | null
  itemsById: Map<number, ItineraryItem>
  keepFirst: boolean
  onKeepFirst: (value: boolean) => void
  pending: 'route' | 'suggest' | 'apply' | null
  message: string
  onSuggest: () => void
  onApply: () => void
  onCancel: () => void
}

const km = (value: number) => `${value.toFixed(value < 10 ? 2 : 1)} km`

function title(itemsById: Map<number, ItineraryItem>, id: number): string {
  return itemsById.get(id)?.title ?? `Item #${id}`
}

function OrderList({ label, ids, total, plan, itemsById }: {
  label: string; ids: number[]; total: number; plan: OptimizePlan; itemsById: Map<number, ItineraryItem>
}) {
  const unlocated = new Set(plan.original_route.unlocated_item_ids)
  return <div className="plan-column">
    <h4>{label} <span className="plan-total">{km(total)}</span></h4>
    <ol>{ids.map((id) => <li key={id}>
      {title(itemsById, id)}
      {plan.anchored_item_ids.includes(id) && <span className="status-badge anchor-badge">
        {unlocated.has(id) ? 'Fixed · no place' : itemsById.get(id)?.start_time ? 'Fixed · timed' : 'Fixed · start'}
      </span>}
    </li>)}</ol>
  </div>
}

export function DayRoutePanel(props: Props) {
  const { route, plan, itemsById } = props
  const saved = plan ? plan.original_route.total_distance_km - plan.proposed_route.total_distance_km : 0
  return <section className="map-card" aria-labelledby="day-route-title">
    <h3 id="day-route-title">Day route</h3>
    <div className="field"><label htmlFor="route-day">Day</label>
      <select id="route-day" value={props.day} onChange={(event) => props.onDay(event.target.value)}>
        {props.days.map((day) => <option key={day} value={day}>{day}</option>)}
      </select></div>
    <p className="route-disclaimer">Straight-line distance, not actual travel distance or time.</p>
    {props.pending === 'route' && <p role="status">Loading route...</p>}
    {route && props.pending !== 'route' && <>
      {route.stops.length === 0
        ? <p className="muted-copy">No itinerary items with a linked place on this day.</p>
        : <ol className="route-legs" aria-label="Route stops">
          {route.stops.map((stop, index) => {
            const leg = route.legs[index - 1]
            return <li key={stop.item_id}>
              {leg && <span className="leg-distance">↓ {km(leg.distance_km)}</span>}
              <span><span className="stop-number">{index + 1}</span>{title(itemsById, stop.item_id)}
                <span className="trip-meta">{stop.name}</span></span>
            </li>
          })}
        </ol>}
      <p className="route-total">Total straight-line distance: <strong>{km(route.total_distance_km)}</strong></p>
      {route.unlocated_item_ids.length > 0 && <div className="unlocated">
        <p className="muted-copy">Not on the map (no linked place):</p>
        <ul>{route.unlocated_item_ids.map((id) => <li key={id}>{title(itemsById, id)}</li>)}</ul>
      </div>}
    </>}
    <div className="optimize-controls">
      <label className="checkbox-label"><input type="checkbox" checked={props.keepFirst}
        onChange={(event) => props.onKeepFirst(event.target.checked)} />Keep the first item as the start</label>
      <button className="primary-button" type="button" disabled={props.pending !== null}
        onClick={props.onSuggest}>{props.pending === 'suggest' ? 'Suggesting...' : 'Suggest shorter order'}</button>
    </div>
    <p className="muted-copy small-copy">Timed items and items without a place stay where they are.
      The suggestion is a heuristic, not a guaranteed shortest route.</p>
    {props.message && <p className="map-status" role="status">{props.message}</p>}
    {plan && plan.changed && <section className="plan-preview" aria-label="Suggested order preview">
      <p className="plan-saving">Suggested order is <strong>{km(saved)}</strong> shorter in straight-line distance
        ({km(plan.original_route.total_distance_km)} → {km(plan.proposed_route.total_distance_km)}).</p>
      <div className="plan-columns">
        <OrderList label="Current" ids={plan.original_item_ids} total={plan.original_route.total_distance_km}
          plan={plan} itemsById={itemsById} />
        <OrderList label="Suggested" ids={plan.proposed_item_ids} total={plan.proposed_route.total_distance_km}
          plan={plan} itemsById={itemsById} />
      </div>
      <p className="muted-copy small-copy">On the map, the dashed line is the suggested order.</p>
      <div className="actions">
        <button className="primary-button" type="button" disabled={props.pending !== null}
          onClick={props.onApply}>{props.pending === 'apply' ? 'Applying...' : 'Apply suggested order'}</button>
        <button className="retry-button" type="button" disabled={props.pending !== null}
          onClick={props.onCancel}>Cancel</button>
      </div>
    </section>}
  </section>
}
