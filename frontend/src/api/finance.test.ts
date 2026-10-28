import { describe, expect, it, vi } from 'vitest'
import { createExpense, deleteExpense, getBalance, listExpenses, updateExpense } from './finance'

const expense = {
  id: 1, trip_id: 12, description: 'Dinner', amount: '100.00', currency: 'USD',
  paid_by_user_id: 1, expense_date: '2026-09-20', split_method: 'equal', created_by_user_id: 1,
  created_at: '2026-09-20T00:00:00Z', version: 1, updated_at: '2026-09-20T00:00:00Z',
  splits: [{ user_id: 1, share_amount: '50.00', weight: null }, { user_id: 2, share_amount: '50.00', weight: null }],
}
const balance = {
  trip_id: 12, currency: 'USD',
  members: [{ user_id: 1, username: 'owner', paid: '100.00', share: '50.00', settled: '0.00', balance: '50.00' },
    { user_id: 2, username: 'member', paid: '0.00', share: '50.00', settled: '0.00', balance: '-50.00' }],
  suggested_settlements: [{ from_user_id: 2, to_user_id: 1, amount: '50.00' }],
  settlement: { transfers: 1, unsettled_members: 2, minimal: true },
}
const payload = {
  description: 'Dinner', amount: '100.00', currency: 'USD', paid_by_user_id: 1,
  expense_date: '2026-09-20', split_method: 'equal' as const, participant_user_ids: [1, 2],
}

describe('finance API adapters', () => {
  it('uses the versioned expense and balance paths', async () => {
    const request = vi.fn()
      .mockResolvedValueOnce([expense])
      .mockResolvedValueOnce(expense)
      .mockResolvedValueOnce({ ...expense, description: 'Updated dinner' })
      .mockResolvedValueOnce(undefined)
      .mockResolvedValueOnce(balance)

    await expect(listExpenses(request, '12')).resolves.toEqual([expense])
    await expect(createExpense(request, '12', payload)).resolves.toEqual(expense)
    await expect(updateExpense(request, '12', 1, payload)).resolves.toMatchObject({ description: 'Updated dinner' })
    await expect(deleteExpense(request, '12', 1)).resolves.toBeUndefined()
    await expect(getBalance(request, '12')).resolves.toEqual(balance)
    expect(request.mock.calls.map(([path]) => path)).toEqual([
      '/api/v1/trips/12/expenses',
      '/api/v1/trips/12/expenses',
      '/api/v1/trips/12/expenses/1',
      '/api/v1/trips/12/expenses/1',
      '/api/v1/trips/12/balances',
    ])
  })

  it('rejects malformed and numeric money responses', async () => {
    await expect(listExpenses(vi.fn().mockResolvedValue([{ ...expense, amount: 100 }]), '12'))
      .rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
    await expect(getBalance(vi.fn().mockResolvedValue({
      ...balance,
      members: [{ ...balance.members[0], balance: '50' }],
    }), '12')).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
  })

  it('reads share weights and split methods, and rejects unknown methods', async () => {
    const shares = {
      ...expense, split_method: 'shares',
      splits: [{ user_id: 1, share_amount: '33.33', weight: 1 }, { user_id: 2, share_amount: '66.67', weight: 2 }],
    }
    await expect(listExpenses(vi.fn().mockResolvedValue([shares]), '12')).resolves.toEqual([shares])
    await expect(listExpenses(vi.fn().mockResolvedValue([{ ...expense, split_method: 'halves' }]), '12'))
      .rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
    await expect(getBalance(vi.fn().mockResolvedValue({ ...balance, settlement: { transfers: 1 } }), '12'))
      .rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
  })

  it('sends the expense version as If-Match when given', async () => {
    const request = vi.fn().mockResolvedValue(expense)
    await updateExpense(request, '12', 3, payload, 5)
    expect(new Headers(request.mock.calls[0][1].headers).get('If-Match')).toBe('"5"')
  })
})
