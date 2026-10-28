import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError } from '../api/client'
import { createExpense, deleteExpense, listExpenses, updateExpense } from '../api/finance'
import { listMembers } from '../api/collaboration'
import { useAuth } from '../auth/AuthContext'
import type { TripMember } from '../types/collaboration'
import type { Expense, ExpenseInput, SplitMethod } from '../types/finance'

type Props = {
  tripId: string
  onChanged?: () => void
  /** Changes when another member changed the expenses; the list reloads in place. */
  refreshKey?: number
}

/** What the form holds. It becomes an ExpenseInput only when submitted. */
type FormValue = {
  description: string
  amount: string
  currency: string
  paid_by_user_id: number
  expense_date: string
  split_method: SplitMethod
  participant_user_ids: number[]
  /** Per participant, as typed: a whole number of shares. */
  weights: Record<number, string>
  /** Per participant, as typed: an exact amount. */
  amounts: Record<number, string>
}

const AMOUNT = /^[0-9]{1,10}(\.[0-9]{1,2})?$/
const WEIGHT = /^[0-9]{1,7}$/
const METHODS: SplitMethod[] = ['equal', 'shares', 'exact']
const METHOD_LABEL: Record<SplitMethod, string> = { equal: 'Equally', shares: 'By shares', exact: 'Exact amounts' }
const METHOD_HINT: Record<SplitMethod, string> = {
  equal: 'Everyone selected pays the same; leftover cents go to the lowest member ids.',
  shares: 'Give each person a number of shares, for example 2 for a couple on one bill.',
  exact: 'Type each person\'s amount. They must add up to the total.',
}
const SPLIT_LABEL: Record<SplitMethod, string> = { equal: 'Split equally', shares: 'Split by shares', exact: 'Exact split' }

/**
 * Whole cents from a decimal string. The form only uses this to tell the user
 * whether exact amounts add up before sending; the server re-checks every sum.
 */
function cents(value: string): number | null {
  if (!AMOUNT.test(value)) return null
  const [whole, fraction = ''] = value.split('.')
  return Number(whole) * 100 + Number((fraction + '00').slice(0, 2))
}

function formatCents(value: number): string {
  const sign = value < 0 ? '-' : ''
  const magnitude = Math.abs(value)
  return `${sign}${Math.floor(magnitude / 100)}.${String(magnitude % 100).padStart(2, '0')}`
}

function emptyExpense(date = ''): FormValue {
  return {
    description: '', amount: '', currency: '', paid_by_user_id: 0, expense_date: date,
    split_method: 'equal', participant_user_ids: [], weights: {}, amounts: {},
  }
}

function expenseValue(expense: Expense): FormValue {
  return {
    description: expense.description,
    amount: expense.amount,
    currency: expense.currency,
    paid_by_user_id: expense.paid_by_user_id,
    expense_date: expense.expense_date,
    split_method: expense.split_method,
    participant_user_ids: expense.splits.map((split) => split.user_id),
    weights: Object.fromEntries(expense.splits.map((split) => [split.user_id, String(split.weight ?? 1)])),
    amounts: Object.fromEntries(expense.splits.map((split) => [split.user_id, split.share_amount])),
  }
}

/** Validates the split and builds the request, or returns the message to show. */
function toPayload(value: FormValue): { payload: ExpenseInput } | { error: string } {
  const base = {
    description: value.description.trim(), amount: value.amount, currency: value.currency.toUpperCase(),
    paid_by_user_id: value.paid_by_user_id, expense_date: value.expense_date, split_method: value.split_method,
  }
  const people = [...value.participant_user_ids].sort((a, b) => a - b)
  if (value.split_method === 'equal') return { payload: { ...base, participant_user_ids: people } }
  if (value.split_method === 'shares') {
    const splits = people.map((user_id) => ({ user_id, weight: Number(value.weights[user_id] ?? '1') }))
    if (splits.some((split, index) => !WEIGHT.test(value.weights[people[index]] ?? '1') || split.weight < 1)) {
      return { error: 'Each number of shares must be a whole number of at least 1.' }
    }
    return { payload: { ...base, splits } }
  }
  const amounts = people.map((user_id) => [user_id, cents(value.amounts[user_id] ?? '')] as const)
  if (amounts.some(([, amount]) => amount === null || amount <= 0)) {
    return { error: 'Each exact amount must be a positive decimal with at most two decimal places.' }
  }
  const assigned = amounts.reduce((sum, [, amount]) => sum + (amount ?? 0), 0)
  const total = cents(value.amount) ?? 0
  if (assigned !== total) {
    return { error: `Exact amounts add up to ${formatCents(assigned)}, not ${formatCents(total)}.` }
  }
  return { payload: { ...base, splits: amounts.map(([user_id, amount]) => ({ user_id, amount: formatCents(amount ?? 0) })) } }
}

function ExpenseForm({
  initial, members, editing, onCancel, onSubmit,
}: {
  initial: FormValue
  members: TripMember[]
  editing: boolean
  onCancel?: () => void
  onSubmit: (value: ExpenseInput) => Promise<void>
}) {
  const [value, setValue] = useState(initial)
  const [message, setMessage] = useState('')
  const [pending, setPending] = useState(false)

  function update(field: 'description' | 'amount' | 'currency' | 'expense_date' | 'paid_by_user_id', next: string) {
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

  function setPart(field: 'weights' | 'amounts', userId: number, next: string) {
    setValue((current) => ({ ...current, [field]: { ...current[field], [userId]: next } }))
  }

  // The hint under exact amounts: how much of the total is assigned so far.
  const exactStatus = useMemo(() => {
    if (value.split_method !== 'exact') return ''
    const total = cents(value.amount)
    const assigned = value.participant_user_ids.reduce((sum, id) => sum + (cents(value.amounts[id] ?? '') ?? 0), 0)
    if (total === null) return `Assigned ${formatCents(assigned)}; enter the total amount above.`
    if (assigned === total) return `Assigned ${formatCents(assigned)} of ${formatCents(total)}: adds up.`
    const diff = total - assigned
    return `Assigned ${formatCents(assigned)} of ${formatCents(total)}; ${diff > 0 ? `${formatCents(diff)} left` : `${formatCents(-diff)} over`}.`
  }, [value])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending) return
    if (!value.description.trim() || value.description.trim().length > 200) {
      setMessage('Description is required and must be 200 characters or fewer.')
      return
    }
    if (!AMOUNT.test(value.amount) || !/[1-9]/.test(value.amount)) {
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
    const built = toPayload(value)
    if ('error' in built) {
      setMessage(built.error)
      return
    }
    setPending(true)
    setMessage('')
    try {
      await onSubmit(built.payload)
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
      <legend>Split among</legend>
      <div className="split-methods" role="radiogroup" aria-label="Split method">
        {METHODS.map((method) => <label key={method}>
          <input type="radio" name="split-method" value={method} checked={value.split_method === method}
            disabled={pending} onChange={() => setValue((current) => ({ ...current, split_method: method }))} />
          <span>{METHOD_LABEL[method]}</span>
        </label>)}
      </div>
      <p className="split-hint">{METHOD_HINT[value.split_method]}</p>
      <div className="participant-list">
        {members.map((member) => {
          const included = value.participant_user_ids.includes(member.user_id)
          return <div className="participant" key={member.user_id}>
            <label>
              <input
                type="checkbox"
                checked={included}
                disabled={pending}
                onChange={() => toggleParticipant(member.user_id)}
              />
              <span>{member.username}</span>
            </label>
            {included && value.split_method === 'shares' && <input
              className="split-input" aria-label={`${member.username} shares`} inputMode="numeric"
              value={value.weights[member.user_id] ?? '1'} disabled={pending}
              onChange={(event) => setPart('weights', member.user_id, event.target.value)} />}
            {included && value.split_method === 'exact' && <input
              className="split-input split-input-amount" aria-label={`${member.username} amount`} inputMode="decimal"
              placeholder="0.00" value={value.amounts[member.user_id] ?? ''} disabled={pending}
              onChange={(event) => setPart('amounts', member.user_id, event.target.value)} />}
          </div>
        })}
      </div>
      {exactStatus && <p className="split-hint split-total" role="status">{exactStatus}</p>}
    </fieldset>
    <div className="actions">
      <button className="primary-button" type="submit" disabled={pending}>{pending ? 'Saving...' : editing ? 'Save expense' : 'Add expense'}</button>
      {onCancel && <button className="retry-button" type="button" disabled={pending} onClick={onCancel}>Cancel</button>}
    </div>
  </form>
}

/** "Split by shares: Mika ×2 40.00, Jonas ×1 20.00" — the server's exact strings. */
function describeSplit(expense: Expense, names: Map<number, string>): string {
  const name = (id: number) => names.get(id) ?? `user #${id}`
  const parts = expense.splits.map((split) => expense.split_method === 'shares'
    ? `${name(split.user_id)} ×${split.weight ?? 1} ${split.share_amount}`
    : `${name(split.user_id)} ${split.share_amount}`)
  return `${SPLIT_LABEL[expense.split_method]}: ${parts.join(', ')}`
}

export function ExpensePanel({ tripId, onChanged, refreshKey = 0 }: Props) {
  const { request } = useAuth()
  const [members, setMembers] = useState<TripMember[]>([])
  const [expenses, setExpenses] = useState<Expense[]>([])
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [message, setMessage] = useState('')
  const [editing, setEditing] = useState<Expense | null>(null)
  const [busy, setBusy] = useState(false)
  const [formVersion, setFormVersion] = useState(0)

  const load = useCallback(async (silent = false) => {
    if (!silent) {
      setStatus('loading')
      setMessage('')
    }
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
    void load(refreshKey > 0)
  }, [load, refreshKey])

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
            <span className="trip-meta">{describeSplit(expense, names)}</span>
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
              let updated: Expense
              try {
                updated = await updateExpense(request, tripId, editing.id, value, editing.version)
              } catch (error) {
                if (!(error instanceof ApiError) || error.code !== 'STALE_VERSION') throw error
                setEditing(null)
                setMessage('This expense was changed by another member while you were editing. The latest version has been loaded; please review it and edit again.')
                await load(true)
                onChanged?.()
                return
              }
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
