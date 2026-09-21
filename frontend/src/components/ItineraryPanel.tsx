import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError } from '../api/client'
import {
  createItineraryItem, deleteItineraryItem, listItinerary, reorderItinerary, updateItineraryItem,
} from '../api/collaboration'
import { useAuth } from '../auth/AuthContext'
import type { ItineraryInput, ItineraryItem } from '../types/collaboration'
import type { Trip } from '../types/trip'

type Props = { trip: Trip }

const blank = (date: string): ItineraryInput => ({
  title: '', date, location: null, start_time: null, end_time: null, notes: null,
})

function formValue(item: ItineraryItem): ItineraryInput {
  return {
    title: item.title,
    date: item.date,
    location: item.location,
    start_time: item.start_time?.slice(0, 5) ?? null,
    end_time: item.end_time?.slice(0, 5) ?? null,
    notes: item.notes,
  }
}

function ItemForm({
  initial, editing, onCancel, onSubmit,
}: {
  initial: ItineraryInput
  editing: boolean
  onCancel?: () => void
  onSubmit: (value: ItineraryInput) => Promise<void>
}) {
  const [value, setValue] = useState(initial)
  const [message, setMessage] = useState('')
  const [pending, setPending] = useState(false)

  useEffect(() => setValue(initial), [initial])

  function update(field: keyof ItineraryInput, next: string) {
    setValue((current) => ({ ...current, [field]: next || null }))
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

export function ItineraryPanel({ trip }: Props) {
  const { request } = useAuth()
  const [items, setItems] = useState<ItineraryItem[]>([])
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [message, setMessage] = useState('')
  const [editing, setEditing] = useState<ItineraryItem | null>(null)

  const load = useCallback(async () => {
    setStatus('loading')
    try {
      setItems(await listItinerary(request, String(trip.id)))
      setStatus('ready')
    } catch (error) {
      setStatus('error')
      setMessage(error instanceof ApiError ? error.message : 'Could not load itinerary.')
    }
  }, [request, trip.id])

  useEffect(() => {
    void load()
  }, [load])

  const grouped = useMemo(() => {
    const groups = new Map<string, ItineraryItem[]>()
    for (const item of items) groups.set(item.date, [...(groups.get(item.date) ?? []), item])
    return [...groups.entries()]
  }, [items])

  async function remove(item: ItineraryItem) {
    if (!window.confirm(`Delete ${item.title}?`)) return
    try {
      await deleteItineraryItem(request, String(trip.id), item.id)
      setItems((current) => current.filter((candidate) => candidate.id !== item.id))
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : 'Could not delete itinerary item.')
    }
  }

  async function move(date: string, index: number, direction: -1 | 1) {
    const group = grouped.find(([day]) => day === date)?.[1] ?? []
    const target = index + direction
    if (target < 0 || target >= group.length) return
    const ids = group.map((item) => item.id)
    ;[ids[index], ids[target]] = [ids[target], ids[index]]
    try {
      const updated = await reorderItinerary(request, String(trip.id), date, ids)
      setItems((current) => [...current.filter((item) => item.date !== date), ...updated]
        .sort((a, b) => a.date.localeCompare(b.date) || a.position - b.position))
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : 'Could not reorder itinerary.')
    }
  }

  return (
    <section className="collab-section itinerary-section" aria-labelledby="itinerary-section-title">
      <div className="section-heading">
        <div><p className="eyebrow">Shared plan</p><h2 id="itinerary-section-title">Itinerary</h2></div>
        <button className="retry-button" type="button" onClick={() => void load()}>Refresh</button>
      </div>
      {status === 'loading' && <p role="status">Loading itinerary...</p>}
      {status === 'error' && <p className="form-error" role="alert">{message}</p>}
      {status === 'ready' && grouped.length === 0 && <p className="muted-copy">No itinerary items yet.</p>}
      {grouped.map(([date, dayItems]) => <section className="itinerary-day" key={date}>
        <h3>{date}</h3>
        <div className="itinerary-list">
          {dayItems.map((item, index) => <article className="itinerary-row" key={item.id}>
            <div><strong>{item.title}</strong>
              <span className="trip-meta">{[item.start_time?.slice(0, 5), item.location].filter(Boolean).join(' · ') || 'No time or location'}</span>
              {item.notes && <p className="muted-copy">{item.notes}</p>}
            </div>
            <div className="actions">
              <button className="icon-button" type="button" title="Move item up" aria-label={`Move ${item.title} up`} disabled={index === 0} onClick={() => void move(date, index, -1)}>↑</button>
              <button className="icon-button" type="button" title="Move item down" aria-label={`Move ${item.title} down`} disabled={index === dayItems.length - 1} onClick={() => void move(date, index, 1)}>↓</button>
              <button className="retry-button" type="button" onClick={() => setEditing(item)}>Edit</button>
              <button className="danger-button" type="button" onClick={() => void remove(item)}>Delete</button>
            </div>
          </article>)}
        </div>
      </section>)}
      {editing ? <section className="trip-editor" aria-labelledby="edit-itinerary-title">
        <h3 id="edit-itinerary-title">Edit itinerary item</h3>
        <ItemForm
          initial={formValue(editing)}
          editing
          onCancel={() => setEditing(null)}
          onSubmit={async (value) => {
            const updated = await updateItineraryItem(request, String(trip.id), editing.id, value)
            setItems((current) => current.map((item) => item.id === updated.id ? updated : item)
              .sort((a, b) => a.date.localeCompare(b.date) || a.position - b.position))
            setEditing(null)
          }}
        />
      </section> : <section className="trip-editor" aria-labelledby="add-itinerary-title">
        <h3 id="add-itinerary-title">Add itinerary item</h3>
        <ItemForm
          initial={blank(trip.start_date)}
          editing={false}
          onSubmit={async (value) => {
            const created = await createItineraryItem(request, String(trip.id), value)
            setItems((current) => [...current, created].sort((a, b) => a.date.localeCompare(b.date) || a.position - b.position))
          }}
        />
      </section>}
      {message && status === 'ready' && <p className="form-error" role="alert">{message}</p>}
    </section>
  )
}
