import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { getBalance } from '../api/finance'
import { useAuth } from '../auth/AuthContext'
import type { Balance } from '../types/finance'

type Props = { tripId: string; refreshKey: number }

export function BalancePanel({ tripId, refreshKey }: Props) {
  const { request } = useAuth()
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
      setMessage(error instanceof ApiError ? error.message : 'Could not load balances.')
    }
  }, [request, tripId])

  useEffect(() => {
    void load()
  }, [load, refreshKey])

  const names = new Map(balance?.members.map((member) => [member.user_id, member.username]) ?? [])

  return (
    <section className="collab-section finance-section" aria-labelledby="balance-title">
      <div className="section-heading">
        <div><p className="eyebrow">Settlement view</p><h2 id="balance-title">Balances</h2></div>
        <button className="retry-button" type="button" disabled={status === 'loading'} onClick={() => void load()}>Refresh balances</button>
      </div>
      {status === 'loading' && <p role="status">Loading balances...</p>}
      {status === 'error' && <p className="form-error" role="alert">{message}</p>}
      {status === 'ready' && balance && <>
        {!balance.currency && <p className="muted-copy">No expenses yet. Balances will appear after the first expense.</p>}
        <div className="balance-list">
          {balance.members.map((member) => {
            const positive = member.balance.startsWith('-') === false && member.balance !== '0.00'
            const zero = member.balance === '0.00'
            return <div className="balance-row" key={member.user_id}>
              <div><strong>{member.username}</strong><span className="trip-meta">Paid {member.paid} · Share {member.share}</span></div>
              <span className={`balance-value ${zero ? 'balance-zero' : positive ? 'balance-positive' : 'balance-negative'}`}>
                {zero ? 'Even' : `${positive ? 'To receive: +' : 'Owes: '}${member.balance} ${balance.currency ?? ''}`}
              </span>
            </div>
          })}
        </div>
        <h3 className="subsection-title">Suggested settlements (not payments)</h3>
        {balance.suggested_settlements.length === 0
          ? <p className="muted-copy">No settlement suggestions.</p>
          : <div className="settlement-list">{balance.suggested_settlements.map((suggestion) => (
            <div className="settlement-row" key={`${suggestion.from_user_id}-${suggestion.to_user_id}-${suggestion.amount}`}>
              <strong>{names.get(suggestion.from_user_id) ?? `user #${suggestion.from_user_id}`} → {names.get(suggestion.to_user_id) ?? `user #${suggestion.to_user_id}`}</strong>
              <span>— {suggestion.amount} {balance.currency ?? ''}</span>
            </div>
          ))}</div>}
      </>}
    </section>
  )
}
