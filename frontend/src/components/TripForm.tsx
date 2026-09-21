import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError } from '../api/client'
import type { TripInput } from '../types/trip'

type Props = {
  initialValue?: TripInput
  submitLabel: string
  pendingLabel: string
  onSubmit: (value: TripInput, signal: AbortSignal) => Promise<void>
  onCancel?: () => void
}

type FieldName = keyof TripInput
type FieldErrors = Partial<Record<FieldName, string>>

const emptyTrip: TripInput = {
  name: '',
  destination: '',
  start_date: '',
  end_date: '',
}

export function TripForm({
  initialValue = emptyTrip,
  submitLabel,
  pendingLabel,
  onSubmit,
  onCancel,
}: Props) {
  const [value, setValue] = useState<TripInput>(initialValue)
  const [errors, setErrors] = useState<FieldErrors>({})
  const [message, setMessage] = useState('')
  const [pending, setPending] = useState(false)
  const activeRequest = useRef<AbortController | null>(null)
  const errorSummary = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setValue(initialValue)
    setErrors({})
    setMessage('')
  }, [initialValue])

  useEffect(() => () => activeRequest.current?.abort(), [])
  useEffect(() => {
    if (message) errorSummary.current?.focus()
  }, [message])

  function update(field: FieldName, fieldValue: string) {
    setValue((current) => ({ ...current, [field]: fieldValue }))
    setErrors((current) => ({ ...current, [field]: undefined }))
  }

  function validate(): FieldErrors {
    const next: FieldErrors = {}
    if (!value.name.trim() || value.name.trim().length > 120) {
      next.name = 'Name is required and must be 120 characters or fewer.'
    }
    if (!value.destination.trim() || value.destination.trim().length > 200) {
      next.destination = 'Destination is required and must be 200 characters or fewer.'
    }
    if (!value.start_date) next.start_date = 'Start date is required.'
    if (!value.end_date) next.end_date = 'End date is required.'
    if (value.start_date && value.end_date && value.end_date < value.start_date) {
      next.end_date = 'End date must be on or after the start date.'
    }
    return next
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (activeRequest.current) return
    const next = validate()
    setErrors(next)
    if (Object.keys(next).length > 0) {
      setMessage('Please check the highlighted fields.')
      return
    }
    const controller = new AbortController()
    activeRequest.current = controller
    setPending(true)
    setMessage('')
    try {
      await onSubmit({
        name: value.name.trim(),
        destination: value.destination.trim(),
        start_date: value.start_date,
        end_date: value.end_date,
      }, controller.signal)
    } catch (error) {
      if (!controller.signal.aborted) {
        if (error instanceof ApiError) {
          const fieldErrors: FieldErrors = {}
          for (const issue of error.details) {
            const field = issue.loc[1]
            if (field === 'name' || field === 'destination' ||
              field === 'start_date' || field === 'end_date') {
              fieldErrors[field] = issue.msg
            }
          }
          setErrors(fieldErrors)
          setMessage(error.message)
        } else {
          setMessage('Could not save this trip. Please try again.')
        }
      }
    } finally {
      activeRequest.current = null
      if (!controller.signal.aborted) setPending(false)
    }
  }

  const input = (field: FieldName, label: string, type = 'text') => (
    <div className="field">
      <label htmlFor={`trip-${field}`}>{label}</label>
      <input
        id={`trip-${field}`}
        type={type}
        required
        disabled={pending}
        value={value[field]}
        onChange={(event) => update(field, event.target.value)}
        aria-invalid={Boolean(errors[field])}
        aria-describedby={errors[field] ? `trip-${field}-error` : undefined}
      />
      {errors[field] && <p className="field-error" id={`trip-${field}-error`}>{errors[field]}</p>}
    </div>
  )

  return (
    <form className="trip-form" onSubmit={submit} noValidate aria-busy={pending}>
      {message && <div className="form-error" role="alert" tabIndex={-1} ref={errorSummary}>{message}</div>}
      {input('name', 'Trip name')}
      {input('destination', 'Destination')}
      <div className="trip-date-grid">
        {input('start_date', 'Start date', 'date')}
        {input('end_date', 'End date', 'date')}
      </div>
      <div className="actions">
        <button className="primary-button" type="submit" disabled={pending}>
          {pending ? pendingLabel : submitLabel}
        </button>
        {onCancel && <button className="retry-button" type="button" disabled={pending} onClick={onCancel}>Cancel</button>}
      </div>
    </form>
  )
}
