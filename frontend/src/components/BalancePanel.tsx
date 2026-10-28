import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { deleteSettlement, getBalance, listSettlements, recordSettlement } from '../api/finance'
import { useAuth } from '../auth/AuthContext'
import type { Balance, Settlement, SettlementSuggestion } from '../types/finance'

type Props = { tripId: string; refreshKey: number; onChanged?: () => void }

function today(): string {
  return new Date().toISOString().slice(0, 10)
}

export function BalancePanel({ tripId, refreshKey, onChanged }: Props) {
  const { request } = useAuth()
  const [balance, setBalance] = useState<Balance | null>(null)
  const [payments, setPayments] = useState<Settlement[]>([])
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async (silent = false) => {
    if (!silent) setStatus('loading')
    try {
      const [nextBalance, nextPayments] = await Promise.all([getBalance(request, tripId), listSettlements(request, tripId)])
      setBalance(nextBalance)
      setPayments(nextPayments)
      setStatus('ready')
    } catch (error) {
      setStatus('error')
      setMessage(error instanceof ApiError ? error.message : 'Could not load balances.')
    }
  }, [request, tripId])

  useEffect(() => {
    void load(refreshKey > 0)
  }, [load, refreshKey])

  const names = new Map(balance?.members.map((member) => [member.user_id, member.username]) ?? [])
  const name = (id: number) => names.get(id) ?? `user #${id}`

  /** Records a suggested transfer as paid today; the balances reload from the server. */
  async function markPaid(suggestion: SettlementSuggestion) {
    if (busy || !balance?.currency) return
    setBusy(true)
    setMessage('')
    try {
      await recordSettlement(request, tripId, {
        from_user_id: suggestion.from_user_id, to_user_id: suggestion.to_user_id,
        amount: suggestion.amount, currency: balance.currency, paid_on: today(),
      })
      await load(true)
      onChanged?.()
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : 'Could not record the payment.')
    } finally {
      setBusy(false)
    }
  }

  async function remove(payment: Settlement) {
    if (busy) return
    if (!window.confirm(`Remove the ${payment.amount} ${payment.currency} payment from ${name(payment.from_user_id)} to ${name(payment.to_user_id)}?`)) return
    setBusy(true)
    setMessage('')
    try {
      await deleteSettlement(request, tripId, payment.id)
      await load(true)
      onChanged?.()
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : 'Could not remove the payment.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="collab-section finance-section" aria-labelledby="balance-title">
      <div className="section-heading">
        <div><p className="eyebrow">Settlement view</p><h2 id="balance-title">Balances</h2></div>
        <button className="retry-button" type="button" disabled={status === 'loading' || busy} onClick={() => void load()}>Refresh balances</button>
      </div>
      {status === 'loading' && <p role="status">Loading balances...</p>}
      {status === 'error' && <p className="form-error" role="alert">{message}</p>}
      {status === 'ready' && balance && <>
        {!balance.currency && <p className="muted-copy">No expenses yet. Balances will appear after the first expense.</p>}
        {message && <p className="form-error" role="alert">{message}</p>}
        <div className="balance-list">
          {balance.members.map((member) => {
            const positive = member.balance.startsWith('-') === false && member.balance !== '0.00'
            const zero = member.balance === '0.00'
            return <div className="balance-row" key={member.user_id}>
              <div><strong>{member.username}</strong><span className="trip-meta">Paid {member.paid} · Share {member.share}{member.settled !== '0.00' && ` · Settled ${member.settled}`}</span></div>
              <span className={`balance-value ${zero ? 'balance-zero' : positive ? 'balance-positive' : 'balance-negative'}`}>
                {zero ? 'Even' : `${positive ? 'To receive: +' : 'Owes: '}${member.balance} ${balance.currency ?? ''}`}
              </span>
            </div>
          })}
        </div>
        <h3 className="subsection-title">Suggested settlements (not payments)</h3>
        {balance.settlement.transfers > 0 && <p className="settlement-summary">
          {balance.settlement.transfers} {balance.settlement.transfers === 1 ? 'transfer settles' : 'transfers settle'}{' '}
          {balance.settlement.unsettled_members} members
          {balance.settlement.minimal ? ', the fewest possible.' : '. The group is too large for an exact search, so this is a greedy plan.'}
        </p>}
        {balance.suggested_settlements.length === 0
          ? <p className="muted-copy">{balance.currency ? 'Everyone is settled up.' : 'No settlement suggestions.'}</p>
          : <div className="settlement-list">{balance.suggested_settlements.map((suggestion) => (
            <div className="settlement-row" key={`${suggestion.from_user_id}-${suggestion.to_user_id}-${suggestion.amount}`}>
              <strong>{name(suggestion.from_user_id)} → {name(suggestion.to_user_id)}</strong>
              <span>— {suggestion.amount} {balance.currency ?? ''}</span>
              <button className="retry-button settlement-action" type="button" disabled={busy}
                aria-label={`Mark ${suggestion.amount} ${balance.currency ?? ''} from ${name(suggestion.from_user_id)} to ${name(suggestion.to_user_id)} as paid`}
                onClick={() => void markPaid(suggestion)}>Mark as paid</button>
            </div>
          ))}</div>}
        {payments.length > 0 && <>
          <h3 className="subsection-title">Payments recorded</h3>
          <div className="settlement-list" aria-label="Payments recorded">{payments.map((payment) => (
            <div className="settlement-row" key={payment.id}>
              <strong>{name(payment.from_user_id)} → {name(payment.to_user_id)}</strong>
              <span>— {payment.amount} {payment.currency} · {payment.paid_on}{payment.note ? ` · ${payment.note}` : ''}</span>
              <button className="danger-button settlement-action" type="button" disabled={busy}
                aria-label={`Remove the payment of ${payment.amount} from ${name(payment.from_user_id)} to ${name(payment.to_user_id)}`}
                onClick={() => void remove(payment)}>Remove</button>
            </div>
          ))}</div>
        </>}
      </>}
    </section>
  )
}
