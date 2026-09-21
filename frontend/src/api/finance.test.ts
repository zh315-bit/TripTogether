import { describe, expect, it, vi } from 'vitest'
import { createExpense, deleteExpense, getBalance, listExpenses, updateExpense } from './finance'

const expense = {
  id: 1, trip_id: 12, description: 'Dinner', amount: '100.00', currency: 'USD',
  paid_by_user_id: 1, expense_date: '2026-09-20', created_by_user_id: 1,
  created_at: '2026-09-20T00:00:00Z', updated_at: '2026-09-20T00:00:00Z',
  splits: [{ user_id: 1, share_amount: '50.00' }, { user_id: 2, share_amount: '50.00' }],
}
const balance = {
  trip_id: 12, currency: 'USD',
  members: [{ user_id: 1, username: 'owner', paid: '100.00', share: '50.00', balance: '50.00' },
    { user_id: 2, username: 'member', paid: '0.00', share: '50.00', balance: '-50.00' }],
  suggested_settlements: [{ from_user_id: 2, to_user_id: 1, amount: '50.00' }],
}
const payload = {
  description: 'Dinner', amount: '100.00', currency: 'USD', paid_by_user_id: 1,
  expense_date: '2026-09-20', participant_user_ids: [1, 2],
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
})
