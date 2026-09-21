import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError } from '../api/client'
import { createExpense, deleteExpense, listExpenses, updateExpense } from '../api/finance'
import { listMembers } from '../api/collaboration'
import { useAuth } from '../auth/AuthContext'
import type { TripMember } from '../types/collaboration'
import type { Expense, ExpenseInput } from '../types/finance'

type Props = { tripId: string; onChanged?: () => void }

function emptyExpense(date = ''): ExpenseInput {
  return {
    description: '',
    amount: '',
    currency: '',
    paid_by_user_id: 0,
    expense_date: date,
    participant_user_ids: [],
  }
}

function expenseValue(expense: Expense): ExpenseInput {
  return {
    description: expense.description,
    amount: expense.amount,
    currency: expense.currency,
    paid_by_user_id: expense.paid_by_user_id,
    expense_date: expense.expense_date,
    participant_user_ids: expense.splits.map((split) => split.user_id),
  }
}

function ExpenseForm({
  initial, members, editing, onCancel, onSubmit,
}: {
  initial: ExpenseInput
  members: TripMember[]
  editing: boolean
  onCancel?: () => void
  onSubmit: (value: ExpenseInput) => Promise<void>
}) {
  const [value, setValue] = useState(initial)
  const [message, setMessage] = useState('')
  const [pending, setPending] = useState(false)

  function update(field: keyof ExpenseInput, next: string) {
    if (field === 'paid_by_user_id') {
      setValue((current) => ({ ...current, paid_by_user_id: Number(next) }))
    } else {
      setValue((current) => ({ ...current, [field]: next }))
    }
  }

  function toggleParticipant(userId: number) {
    setValue((current) => ({
      ...current,
      participant_user_ids: current.participant_user_ids.includes(userId)
        ? current.participant_user_ids.filter((id) => id !== userId)
        : [...current.participant_user_ids, userId].sort((a, b) => a - b),
    }))
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending) return
    if (!value.description.trim() || value.description.trim().length > 200) {
      setMessage('Description is required and must be 200 characters or fewer.')
      return
    }
    if (!/^[0-9]{1,10}(\.[0-9]{1,2})?$/.test(value.amount) || !/[1-9]/.test(value.amount)) {
      setMessage('Amount must be a positive decimal with at most two decimal places.')
      return
    }
    if (!/^[A-Z]{3}$/.test(value.currency)) {
      setMessage('Currency must be three uppercase letters.')
      return
    }
    if (!value.paid_by_user_id || !value.expense_date) {
      setMessage('Payer and expense date are required.')
      return
    }
    if (value.participant_user_ids.length === 0) {
      setMessage('Select at least one participant.')
      return
    }
    setPending(true)
    setMessage('')
    try {
      await onSubmit({ ...value, description: value.description.trim(), currency: value.currency.toUpperCase() })
    } catch (error) {
      setMessage(error instanceof ApiError
        ? [error.message, ...error.details.map((issue) => issue.msg)].join(' ')
        : 'Could not save this expense.')
    } finally {
      setPending(false)
    }
  }

  return <form className="expense-form" onSubmit={submit}>
    {message && <p className="form-error" role="alert">{message}</p>}
    <div className="expense-form-grid">
      <div className="field"><label htmlFor="expense-description">Description</label><input
        id="expense-description" value={value.description} disabled={pending}
        onChange={(event) => update('description', event.target.value)} /></div>
      <div className="field"><label htmlFor="expense-amount">Amount</label><input
        id="expense-amount" inputMode="decimal" placeholder="120.00" value={value.amount} disabled={pending}
        onChange={(event) => update('amount', event.target.value)} /></div>
      <div className="field"><label htmlFor="expense-currency">Currency</label><input
        id="expense-currency" maxLength={3} placeholder="USD" value={value.currency} disabled={pending}
        onChange={(event) => update('currency', event.target.value.toUpperCase())} /></div>
      <div className="field"><label htmlFor="expense-date">Expense date</label><input
        id="expense-date" type="date" value={value.expense_date} disabled={pending}
        onChange={(event) => update('expense_date', event.target.value)} /></div>
      <div className="field"><label htmlFor="expense-payer">Paid by</label><select
        id="expense-payer" value={value.paid_by_user_id || ''} disabled={pending}
        onChange={(event) => update('paid_by_user_id', event.target.value)}>
        <option value="" disabled>Select a payer</option>
        {members.map((member) => <option value={member.user_id} key={member.user_id}>{member.username}</option>)}
      </select></div>
    </div>
    <fieldset className="participant-fieldset">
      <legend>Split equally among</legend>
      <div className="participant-list">
        {members.map((member) => <label key={member.user_id}>
          <input
            type="checkbox"
            checked={value.participant_user_ids.includes(member.user_id)}
            disabled={pending}
            onChange={() => toggleParticipant(member.user_id)}
          />
          <span>{member.username}</span>
        </label>)}
      </div>
    </fieldset>
    <div className="actions">
      <button className="primary-button" type="submit" disabled={pending}>{pending ? 'Saving...' : editing ? 'Save expense' : 'Add expense'}</button>
      {onCancel && <button className="retry-button" type="button" disabled={pending} onClick={onCancel}>Cancel</button>}
    </div>
  </form>
}

export function ExpensePanel({ tripId, onChanged }: Props) {
  const { request } = useAuth()
  const [members, setMembers] = useState<TripMember[]>([])
  const [expenses, setExpenses] = useState<Expense[]>([])
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [message, setMessage] = useState('')
  const [editing, setEditing] = useState<Expense | null>(null)
  const [busy, setBusy] = useState(false)
  const [formVersion, setFormVersion] = useState(0)

  const load = useCallback(async () => {
    setStatus('loading')
    setMessage('')
    try {
      const [memberList, expenseList] = await Promise.all([
        listMembers(request, tripId),
        listExpenses(request, tripId),
      ])
      setMembers(memberList)
      setExpenses(expenseList)
      setStatus('ready')
    } catch (error) {
      setStatus('error')
      setMessage(error instanceof ApiError ? error.message : 'Could not load expenses.')
    }
  }, [request, tripId])

  useEffect(() => {
    void load()
  }, [load])

  const names = useMemo(() => new Map(members.map((member) => [member.user_id, member.username])), [members])
  const initial = editing
    ? expenseValue(editing)
    : emptyExpense()

  async function remove(expense: Expense) {
    if (busy) return
    if (!window.confirm(`Delete ${expense.description}?`)) return
    setBusy(true)
    setMessage('')
    try {
      await deleteExpense(request, tripId, expense.id)
      setExpenses((current) => current.filter((item) => item.id !== expense.id))
      if (editing?.id === expense.id) setEditing(null)
      onChanged?.()
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : 'Could not delete this expense.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="collab-section finance-section" aria-labelledby="expenses-title">
      <div className="section-heading">
        <div><p className="eyebrow">Shared costs</p><h2 id="expenses-title">Expenses</h2></div>
        <button className="retry-button" type="button" disabled={busy || status === 'loading'} onClick={() => void load()}>Refresh expenses</button>
      </div>
      {status === 'loading' && <p role="status">Loading expenses...</p>}
      {status === 'error' && <p className="form-error" role="alert">{message}</p>}
      {status === 'ready' && expenses.length === 0 && <p className="muted-copy">No expenses yet.</p>}
      {status === 'ready' && expenses.length > 0 && <div className="expense-list">
        {expenses.map((expense) => <article className="expense-row" key={expense.id}>
          <div>
            <strong>{expense.description}</strong>
            <span className="trip-meta">{expense.expense_date} · Paid by {names.get(expense.paid_by_user_id) ?? `user #${expense.paid_by_user_id}`}</span>
            <span className="trip-meta">Split: {expense.splits.map((split) => `${names.get(split.user_id) ?? `user #${split.user_id}`} ${split.share_amount}`).join(', ')}</span>
          </div>
          <div className="expense-amount">
            <strong>{expense.amount} {expense.currency}</strong>
            <div className="actions">
              <button className="retry-button" type="button" disabled={busy} onClick={() => setEditing(expense)}>Edit expense</button>
              <button className="danger-button" type="button" disabled={busy} onClick={() => void remove(expense)}>Delete expense</button>
            </div>
          </div>
        </article>)}
      </div>}
      {status === 'ready' && <section className="trip-editor" aria-labelledby={editing ? 'edit-expense-title' : 'add-expense-title'}>
        <h3 id={editing ? 'edit-expense-title' : 'add-expense-title'}>{editing ? 'Edit expense' : 'Add expense'}</h3>
        <ExpenseForm
          key={editing?.id ?? `new-${formVersion}`}
          initial={initial}
          members={members}
          editing={Boolean(editing)}
          onCancel={editing ? () => setEditing(null) : undefined}
          onSubmit={async (value) => {
            setBusy(true)
            setMessage('')
            try {
            if (editing) {
              const updated = await updateExpense(request, tripId, editing.id, value)
              setExpenses((current) => current.map((item) => item.id === updated.id ? updated : item))
              setEditing(null)
            } else {
              const created = await createExpense(request, tripId, value)
              setExpenses((current) => [created, ...current])
              setFormVersion((version) => version + 1)
            }
            onChanged?.()
            } finally {
              setBusy(false)
            }
          }}
        />
      </section>}
      {message && status === 'ready' && <p className="form-error" role="alert">{message}</p>}
    </section>
  )
}
