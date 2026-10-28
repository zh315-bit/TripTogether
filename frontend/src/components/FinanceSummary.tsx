import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { getBalance } from '../api/finance'
import { useAuth } from '../auth/AuthContext'
import type { Balance } from '../types/finance'

type Props = {
  tripId: string
  /** Changes after any expense edit, so the summary reloads with the list. */
  refreshKey: number
  onOpenBalances?: () => void
}

/**
 * The signed-in member's position at a glance. Every amount is the server's exact
 * string; the browser only picks which one to show and drops the minus sign.
 */
export function FinanceSummary({ tripId, refreshKey, onOpenBalances }: Props) {
  const { request, state } = useAuth()
  const userId = state.status === 'authenticated' ? state.user.id : null
  const [balance, setBalance] = useState<Balance | null>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [message, setMessage] = useState('')

  const load = useCallback(async () => {
    setStatus('loading')
    try {
      setBalance(await getBalance(request, tripId))
      setStatus('ready')
    } catch (error) {
      setStatus('error')
      setMessage(error instanceof ApiError ? error.message : 'Could not load your summary.')
    }
  }, [request, tripId])

  useEffect(() => {
    void load()
  }, [load, refreshKey])

  if (status === 'loading' && !balance) return <p role="status">Loading your summary...</p>
  if (status === 'error') return <div className="inline-error" role="alert"><p>{message}</p>
    <button className="retry-button" type="button" onClick={() => void load()}>Try again</button></div>
  const me = balance?.members.find((member) => member.user_id === userId)
  if (!balance || !me) return null
  if (!balance.currency) {
    return <p className="finance-summary-empty muted-copy">No expenses yet. Your share and balance appear here
      after the first expense.</p>
  }

  const currency = balance.currency
  const owes = me.balance.startsWith('-')
  const square = me.balance === '0.00'
  const names = new Map(balance.members.map((member) => [member.user_id, member.username]))
  const name = (id: number) => names.get(id) ?? `user #${id}`
  const mine = balance.suggested_settlements.filter((item) => item.from_user_id === me.user_id || item.to_user_id === me.user_id)

  return <section className="finance-summary" aria-label="Your expense summary">
    <div className={`summary-card summary-headline ${square ? 'is-square' : owes ? 'is-owing' : 'is-owed'}`}>
      <p className="summary-label">{square ? "You're all square" : owes ? 'You owe' : "You're owed"}</p>
      <p className="summary-amount">{square ? '✓' : `${owes ? me.balance.slice(1) : me.balance} ${currency}`}</p>
      <p className="trip-meta">{square ? 'Nothing to settle for you right now.' : owes ? 'You should pay others.' : 'Others should pay you.'}</p>
    </div>
    <div className="summary-card"><p className="summary-label">You paid</p>
      <p className="summary-amount summary-amount-small">{me.paid} {currency}</p></div>
    <div className="summary-card"><p className="summary-label">Your share</p>
      <p className="summary-amount summary-amount-small">{me.share} {currency}</p></div>
    {mine.length > 0 && <ul className="summary-transfers" aria-label="Your suggested transfers">
      {mine.map((item) => <li key={`${item.from_user_id}-${item.to_user_id}-${item.amount}`}>
        {item.from_user_id === me.user_id ? `Pay ${name(item.to_user_id)}` : `${name(item.from_user_id)} pays you`}
        <strong>{item.amount} {currency}</strong>
      </li>)}
    </ul>}
    {onOpenBalances && <button className="place-link-button summary-link" type="button" onClick={onOpenBalances}>
      See everyone's balances</button>}
  </section>
}
