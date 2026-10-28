import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import {
  closestCenter, DndContext, KeyboardSensor, PointerSensor, useSensor, useSensors,
} from '@dnd-kit/core'
import type { DragEndEvent } from '@dnd-kit/core'
import {
  arrayMove, SortableContext, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { ApiError } from '../api/client'
import {
  createItineraryItem, deleteItineraryItem, listItinerary, reorderItinerary, updateItineraryItem,
} from '../api/collaboration'
import { listPlaces } from '../api/places'
import { useAuth } from '../auth/AuthContext'
import type { ItineraryInput, ItineraryItem } from '../types/collaboration'
import type { DayRoute, RouteLeg, TripPlace } from '../types/places'
import { km } from './map/distance'
import type { Trip } from '../types/trip'

/** The straight-line hop into an item; names the origin when an unlocated item sits between. */
function LegDistance({ leg, previous, items }: { leg?: RouteLeg; previous?: ItineraryItem; items: ItineraryItem[] }) {
  // A stale route (mid-reload after an edit) may point at items no longer on this day.
  const from = leg && items.find((item) => item.id === leg.from_item_id)
  if (!leg || !from) return null
  return <p className="itinerary-leg" title="Straight-line distance, not travel distance">
    <span aria-hidden="true">↓ </span>{km(leg.distance_km)}{from.id === previous?.id ? '' : ` from ${from.title}`}
  </p>
}

/** One draggable row; only the handle starts a drag, so buttons and links keep working. */
function SortableRow({ id, title, disabled, className, onMouseEnter, onMouseLeave, children }: {
  id: number
  title: string
  disabled: boolean
  className: string
  onMouseEnter?: () => void
  onMouseLeave?: () => void
  children: ReactNode
}) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } =
    useSortable({ id, disabled })
  return <article ref={setNodeRef} className={`${className}${isDragging ? ' is-dragging' : ''}`}
    style={{ transform: CSS.Translate.toString(transform), transition }}
    onMouseEnter={onMouseEnter} onMouseLeave={onMouseLeave}>
    <button ref={setActivatorNodeRef} className="drag-handle" type="button" disabled={disabled}
      {...attributes} {...listeners} aria-label={`Drag ${title} to reorder`} title="Drag to reorder">
      <span aria-hidden="true">⠿</span></button>
    {children}
  </article>
}

type Props = {
  trip: Trip
  /** The workspace's place pool; when given, the panel does not fetch its own copy. */
  places?: TripPlace[]
  /** Called after any successful itinerary change, so the map can redraw the route. */
  onChanged?: () => void
  /** Changes when the itinerary was changed outside this panel (e.g. an applied route). */
  refreshKey?: number
  /** Linked places are highlighted and selectable, in sync with the map. */
  selectedPlaceId?: number | null
  onSelectPlace?: (placeId: number) => void
  onHoverPlace?: (placeId: number | null) => void
  /** The map's selected day route: its legs are shown between that day's rows. */
  route?: DayRoute | null
  /** Makes another day the map's route day, so its distances appear here. */
  onShowDay?: (date: string) => void
}

const blank = (date: string): ItineraryInput => ({
  title: '', date, location: null, start_time: null, end_time: null, notes: null, place_id: null,
})

function formValue(item: ItineraryItem): ItineraryInput {
  return {
    title: item.title,
    date: item.date,
    location: item.location,
    start_time: item.start_time?.slice(0, 5) ?? null,
    end_time: item.end_time?.slice(0, 5) ?? null,
    notes: item.notes,
    place_id: item.place_id,
  }
}

function ItemForm({
  initial, editing, places, onCancel, onSubmit,
}: {
  initial: ItineraryInput
  editing: boolean
  places: TripPlace[]
  onCancel?: () => void
  onSubmit: (value: ItineraryInput) => Promise<void>
}) {
  const [value, setValue] = useState(initial)
  const [message, setMessage] = useState('')
  const [pending, setPending] = useState(false)

  useEffect(() => setValue(initial), [initial])

  function update(field: Exclude<keyof ItineraryInput, 'place_id'>, next: string) {
    setValue((current) => ({ ...current, [field]: next || null }))
  }

  function choosePlace(next: string) {
    const placeId = next ? Number(next) : null
    setValue((current) => {
      const previous = places.find((place) => place.id === current.place_id)?.name
      const chosen = places.find((place) => place.id === placeId)?.name
      // Follow the chosen place unless the user typed their own location text.
      const followsPlace = !current.location || current.location === previous
      return { ...current, place_id: placeId, location: followsPlace && chosen ? chosen : current.location }
    })
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!value.title.trim() || !value.date) {
      setMessage('Title and date are required.')
      return
    }
    if (value.end_time && (!value.start_time || value.end_time < value.start_time)) {
      setMessage('End time must be on or after the start time.')
      return
    }
    setPending(true)
    setMessage('')
    try {
      await onSubmit({ ...value, title: value.title.trim() })
      if (!editing) setValue(blank(value.date))
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : 'Could not save itinerary item.')
    } finally {
      setPending(false)
    }
  }

  return <form className="itinerary-form" onSubmit={submit}>
    {message && <p className="form-error" role="alert">{message}</p>}
    <div className="itinerary-form-grid">
      <div className="field"><label htmlFor="itinerary-title">Title</label><input
        id="itinerary-title" value={value.title} disabled={pending}
        onChange={(event) => update('title', event.target.value)} /></div>
      <div className="field"><label htmlFor="itinerary-date">Date</label><input
        id="itinerary-date" type="date" value={value.date} disabled={pending}
        onChange={(event) => update('date', event.target.value)} /></div>
      <div className="field"><label htmlFor="itinerary-location">Location</label><input
        id="itinerary-location" value={value.location ?? ''} disabled={pending}
        onChange={(event) => update('location', event.target.value)} /></div>
      <div className="field"><label htmlFor="itinerary-place">Linked place</label><select
        id="itinerary-place" value={value.place_id ?? ''} disabled={pending}
        onChange={(event) => choosePlace(event.target.value)}>
        <option value="">None</option>
        {/* Keep a stale selection visible if its place was deleted meanwhile. */}
        {value.place_id !== null && !places.some((place) => place.id === value.place_id)
          && <option value={value.place_id}>Unavailable place</option>}
        {places.map((place) => <option key={place.id} value={place.id}>{place.name}</option>)}
      </select></div>
      <div className="field"><label htmlFor="itinerary-start">Start time</label><input
        id="itinerary-start" type="time" value={value.start_time ?? ''} disabled={pending}
        onChange={(event) => update('start_time', event.target.value)} /></div>
      <div className="field"><label htmlFor="itinerary-end">End time</label><input
        id="itinerary-end" type="time" value={value.end_time ?? ''} disabled={pending}
        onChange={(event) => update('end_time', event.target.value)} /></div>
      <div className="field"><label htmlFor="itinerary-notes">Notes</label><textarea
        id="itinerary-notes" value={value.notes ?? ''} disabled={pending}
        onChange={(event) => update('notes', event.target.value)} /></div>
    </div>
    <div className="actions">
      <button className="primary-button" type="submit" disabled={pending}>{pending ? 'Saving...' : editing ? 'Save item' : 'Add item'}</button>
      {onCancel && <button className="retry-button" type="button" disabled={pending} onClick={onCancel}>Cancel</button>}
    </div>
  </form>
}

export function ItineraryPanel({
  trip, places: sharedPlaces, onChanged, refreshKey = 0, selectedPlaceId = null, onSelectPlace, onHoverPlace,
  route = null, onShowDay,
}: Props) {
  const { request } = useAuth()
  const [items, setItems] = useState<ItineraryItem[]>([])
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [message, setMessage] = useState('')
  const [editing, setEditing] = useState<ItineraryItem | null>(null)
  const [fetchedPlaces, setPlaces] = useState<TripPlace[]>([])
  const places = sharedPlaces ?? fetchedPlaces
  // The day being dragged (its distance lines hide meanwhile) and a reorder in flight.
  const [draggingDay, setDraggingDay] = useState<string | null>(null)
  const [reordering, setReordering] = useState(false)
  const sensors = useSensors(
    // A few pixels of travel before a drag starts, so a click on the handle stays a click.
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  const load = useCallback(async (silent = false) => {
    // A silent reload (another member's change) keeps the list on screen meanwhile.
    if (!silent) setStatus('loading')
    try {
      setItems(await listItinerary(request, String(trip.id)))
      setStatus('ready')
    } catch (error) {
      setStatus('error')
      setMessage(error instanceof ApiError ? error.message : 'Could not load itinerary.')
    }
  }, [request, trip.id])

  useEffect(() => {
    void load(refreshKey > 0)
  }, [load, refreshKey])

  useEffect(() => {
    // Optional: without places the form still works, just with "None" only.
    if (sharedPlaces) return
    listPlaces(request, String(trip.id)).then(setPlaces, () => setPlaces([]))
  }, [request, trip.id, sharedPlaces])

  const placeNames = useMemo(() => new Map(places.map((place) => [place.id, place.name])), [places])
  // Stable initial values: ItemForm resets whenever `initial` changes identity, so
  // unrelated re-renders (e.g. places finishing loading) must not wipe typed input.
  const blankItem = useMemo(() => blank(trip.start_date), [trip.start_date])
  const editingValue = useMemo(() => editing && formValue(editing), [editing])

  const grouped = useMemo(() => {
    const groups = new Map<string, ItineraryItem[]>()
    for (const item of items) groups.set(item.date, [...(groups.get(item.date) ?? []), item])
    return [...groups.entries()]
  }, [items])

  // Legs join consecutive *located* items, so one may skip an item without a place.
  const legsTo = useMemo(() => new Map<number, RouteLeg>(
    (route?.legs ?? []).map((leg) => [leg.to_item_id, leg])), [route])

  async function remove(item: ItineraryItem) {
    if (!window.confirm(`Delete ${item.title}?`)) return
    try {
      await deleteItineraryItem(request, String(trip.id), item.id)
      setItems((current) => current.filter((candidate) => candidate.id !== item.id))
      onChanged?.()
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : 'Could not delete itinerary item.')
    }
  }

  /** Moves one item within its day; both the arrow buttons and drag and drop end here. */
  async function reorder(date: string, from: number, to: number) {
    const group = grouped.find(([day]) => day === date)?.[1] ?? []
    if (from === to || to < 0 || to >= group.length) return
    const shown = group.map((item) => item.id)
    const ids = arrayMove(shown, from, to)
    const before = items
    // Show the new order at once, so a dropped row does not jump back while saving.
    const moved = arrayMove(group, from, to).map((item, position) => ({ ...item, position: position + 1 }))
    setItems((current) => [...current.filter((item) => item.date !== date), ...moved]
      .sort((a, b) => a.date.localeCompare(b.date) || a.position - b.position))
    setMessage('')
    setReordering(true)
    try {
      const updated = await reorderItinerary(request, String(trip.id), date, ids, shown)
      onChanged?.()
      setItems((current) => [...current.filter((item) => item.date !== date), ...updated]
        .sort((a, b) => a.date.localeCompare(b.date) || a.position - b.position))
    } catch (error) {
      if (error instanceof ApiError && error.code === 'ITINERARY_CONFLICT') {
        // Another member changed this day; show their version instead of retrying.
        setMessage('This day was changed by another member. The latest itinerary has been loaded.')
        await load()
        onChanged?.()
        return
      }
      setItems(before)
      setMessage(error instanceof ApiError ? error.message : 'Could not reorder itinerary.')
    } finally {
      setReordering(false)
    }
  }

  function drop(date: string, dayItems: ItineraryItem[], event: DragEndEvent) {
    setDraggingDay(null)
    const { active, over } = event
    if (!over) return
    const from = dayItems.findIndex((item) => item.id === active.id)
    const to = dayItems.findIndex((item) => item.id === over.id)
    if (from >= 0 && to >= 0) void reorder(date, from, to)
  }

  return (
    <section className="collab-section itinerary-section" aria-labelledby="itinerary-section-title">
      <div className="section-heading">
        <div><p className="eyebrow">Shared plan</p><h2 id="itinerary-section-title">Itinerary</h2></div>
        <button className="retry-button" type="button" onClick={() => void load()}>Refresh</button>
      </div>
      {status === 'loading' && <p role="status">Loading itinerary...</p>}
      {status === 'error' && <p className="form-error" role="alert">{message}</p>}
      {/* Conflicts and failures show here, above the list, where the user is looking. */}
      {message && status === 'ready' && <p className="form-error" role="alert">{message}</p>}
      {status === 'ready' && grouped.length === 0 && <p className="muted-copy">No itinerary items yet.</p>}
      {grouped.map(([date, dayItems]) => <section className="itinerary-day" key={date}>
        <div className="itinerary-day-heading">
          <h3>{date}</h3>
          {route?.date === date
            ? route.legs.length > 0 && <span className="trip-meta">{km(route.total_distance_km)} straight-line</span>
            : onShowDay && <button className="place-link-button" type="button" onClick={() => onShowDay(date)}
              aria-label={`Show the route and distances for ${date}`}>Show distances</button>}
        </div>
        <DndContext sensors={sensors} collisionDetection={closestCenter}
          onDragStart={() => setDraggingDay(date)} onDragCancel={() => setDraggingDay(null)}
          onDragEnd={(event) => drop(date, dayItems, event)}>
        <SortableContext items={dayItems.map((item) => item.id)} strategy={verticalListSortingStrategy}>
        <div className="itinerary-list">
          {dayItems.map((item, index) => <Fragment key={item.id}>
            {route?.date === date && draggingDay !== date && <LegDistance leg={legsTo.get(item.id)}
              previous={dayItems[index - 1]} items={dayItems} />}
            <SortableRow id={item.id} title={item.title} disabled={reordering || dayItems.length < 2}
              className={`itinerary-row${item.place_id !== null && item.place_id === selectedPlaceId ? ' is-selected' : ''}`}
              onMouseEnter={item.place_id === null ? undefined : () => onHoverPlace?.(item.place_id)}
              onMouseLeave={item.place_id === null ? undefined : () => onHoverPlace?.(null)}>
              <div><strong>{item.title}</strong>
                <span className="trip-meta">{[item.start_time?.slice(0, 5), item.location].filter(Boolean).join(' · ') || 'No time or location'}</span>
                {item.place_id !== null && (onSelectPlace
                  ? <button className="place-link-button" type="button" onClick={() => onSelectPlace(item.place_id!)}
                    aria-label={`Show ${placeNames.get(item.place_id) ?? 'linked place'} on the map`}>
                    Place: {placeNames.get(item.place_id) ?? 'linked place'}</button>
                  : <span className="trip-meta">Place: {placeNames.get(item.place_id) ?? 'linked place'}</span>)}
                {item.notes && <p className="muted-copy">{item.notes}</p>}
              </div>
              <div className="actions">
                <button className="icon-button" type="button" title="Move item up" aria-label={`Move ${item.title} up`} disabled={index === 0 || reordering} onClick={() => void reorder(date, index, index - 1)}>↑</button>
                <button className="icon-button" type="button" title="Move item down" aria-label={`Move ${item.title} down`} disabled={index === dayItems.length - 1 || reordering} onClick={() => void reorder(date, index, index + 1)}>↓</button>
                <button className="retry-button" type="button" onClick={() => setEditing(item)}>Edit</button>
                <button className="danger-button" type="button" onClick={() => void remove(item)}>Delete</button>
              </div>
            </SortableRow>
          </Fragment>)}
        </div>
        </SortableContext>
        </DndContext>
      </section>)}
      {editing ? <section className="trip-editor" aria-labelledby="edit-itinerary-title">
        <h3 id="edit-itinerary-title">Edit itinerary item</h3>
        <ItemForm
          initial={editingValue || formValue(editing)}
          editing
          places={places}
          onCancel={() => setEditing(null)}
          onSubmit={async (value) => {
            try {
              const updated = await updateItineraryItem(request, String(trip.id), editing.id, value, editing.version)
              onChanged?.()
              setItems((current) => current.map((item) => item.id === updated.id ? updated : item)
                .sort((a, b) => a.date.localeCompare(b.date) || a.position - b.position))
              setEditing(null)
            } catch (error) {
              if (!(error instanceof ApiError) || error.code !== 'STALE_VERSION') throw error
              // The edit was based on an older version: show the newest one instead of overwriting it.
              setEditing(null)
              setMessage('This item was changed by another member while you were editing. The latest version has been loaded; please review it and edit again.')
              await load(true)
              onChanged?.()
            }
          }}
        />
      </section> : <section className="trip-editor" aria-labelledby="add-itinerary-title">
        <h3 id="add-itinerary-title">Add itinerary item</h3>
        <ItemForm
          initial={blankItem}
          editing={false}
          places={places}
          onSubmit={async (value) => {
            const created = await createItineraryItem(request, String(trip.id), value)
            setItems((current) => [...current, created].sort((a, b) => a.date.localeCompare(b.date) || a.position - b.position))
            onChanged?.()
          }}
        />
      </section>}
    </section>
  )
}
