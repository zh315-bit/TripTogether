import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { AuthProvider } from '../auth/AuthContext'
import { TOKEN_KEY } from '../auth/tokenStorage'
import { ExpensePanel } from './ExpensePanel'
import { BalancePanel } from './BalancePanel'
import { getBalance, listExpenses } from '../api/finance'

const members = [1, 2, 3].map((id) => ({
  user_id: id, username: `Person${id}`, email: `p${id}@example.com`,
  role: 'member', joined_at: '2026-09-20T00:00:00Z',
}))
const expense = {
  id: 1, trip_id: 12, description: 'Dinner', amount: '100.00', currency: 'USD',
  paid_by_user_id: 1, expense_date: '2026-09-20', created_by_user_id: 2,
  created_at: '2026-09-20T00:00:00Z', updated_at: '2026-09-20T00:00:00Z',
  splits: [{ user_id: 1, share_amount: '33.34' }, { user_id: 2, share_amount: '33.33' },
    { user_id: 3, share_amount: '33.33' }],
}
const balance = {
  trip_id: 12, currency: 'USD',
  members: [{ user_id: 1, username: 'Person1', paid: '100.00', share: '33.34', balance: '66.66' },
    { user_id: 2, username: 'Person2', paid: '0.00', share: '33.33', balance: '-33.33' }],
  suggested_settlements: [{ from_user_id: 2, to_user_id: 1, amount: '33.33' }],
}
const json = (data: unknown) => new Response(JSON.stringify(data))

function mount() {
  const onChanged = vi.fn()
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith('/me')) return json({ id: 2, username: 'Person2', email: 'p2@example.com', created_at: expense.created_at })
    if (url.endsWith('/members')) return json(members)
    if (url.endsWith('/balances')) return json(balance)
    if (init?.method === 'DELETE') return new Response(null, { status: 204 })
    if (init?.method) return json({ ...expense, ...JSON.parse(String(init.body)) })
    return json([expense])
  })
  vi.stubGlobal('fetch', fetcher)
  sessionStorage.setItem(TOKEN_KEY, 'test-token')
  // Mount feature panels after the same authenticated boundary used in the app.
  render(<AuthProvider><Ready onChanged={onChanged} /></AuthProvider>)
  return { fetcher, onChanged }
}

import { useAuth } from '../auth/AuthContext'
function Ready({ onChanged }: { onChanged: () => void }) {
  const { state } = useAuth()
  return state.status === 'authenticated' ? <>
    <ExpensePanel tripId="12" onChanged={onChanged} />
    <BalancePanel tripId="12" refreshKey={0} />
  </> : null
}

it('renders exact stored remainders, negative balances and suggested transfers', async () => {
  mount()
  expect(await screen.findByText(/Person1 33.34, Person2 33.33, Person3 33.33/)).toBeInTheDocument()
  expect(await screen.findByText('Owes: -33.33 USD')).toBeInTheDocument()
  expect(screen.getByText('Suggested settlements (not payments)')).toBeInTheDocument()
})

it('rejects zero and precision errors without posting', async () => {
  const { fetcher } = mount()
  await screen.findByLabelText('Description')
  fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'Food' } })
  for (const amount of ['0.00', '1.001', '1e2', '-2']) {
    fireEvent.change(screen.getByLabelText('Amount'), { target: { value: amount } })
    await userEvent.click(screen.getByRole('button', { name: 'Add expense' }))
    expect(screen.getByRole('alert')).toHaveTextContent('positive decimal')
  }
  expect(fetcher.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false)
})

it('sends amount as a string with selected payer and participants', async () => {
  const { fetcher, onChanged } = mount()
  await screen.findByLabelText('Description')
  for (const [label, value] of Object.entries({
    Description: 'Food', Amount: '100.00', Currency: 'USD', 'Expense date': '2026-09-20',
  })) fireEvent.change(screen.getByLabelText(label), { target: { value } })
  await userEvent.selectOptions(screen.getByLabelText('Paid by'), '1')
  await userEvent.click(screen.getByLabelText('Person2'))
  await userEvent.click(screen.getByRole('button', { name: 'Add expense' }))
  await waitFor(() => expect(onChanged).toHaveBeenCalledOnce())
  const body = fetcher.mock.calls.find(([, init]) => init?.method === 'POST')?.[1]?.body
  expect(JSON.parse(String(body))).toMatchObject({ amount: '100.00', paid_by_user_id: 1, participant_user_ids: [2] })
  expect(screen.getByLabelText('Description')).toHaveValue('')
})

it('allows a member to edit another creator expense and delete after confirmation', async () => {
  const { fetcher, onChanged } = mount()
  await userEvent.click(await screen.findByRole('button', { name: 'Edit expense' }))
  fireEvent.change(screen.getByLabelText('Amount'), { target: { value: '90.00' } })
  await userEvent.click(screen.getByRole('button', { name: 'Save expense' }))
  await waitFor(() => expect(onChanged).toHaveBeenCalledOnce())
  expect(fetcher.mock.calls.some(([, init]) => init?.method === 'PATCH')).toBe(true)
  vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true)
  await userEvent.click(screen.getByRole('button', { name: 'Delete expense' }))
  expect(fetcher.mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(false)
  await userEvent.click(screen.getByRole('button', { name: 'Delete expense' }))
  await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(2))
  expect(screen.getByText('No expenses yet.')).toBeInTheDocument()
})

it('accepts signed server balances and rejects numeric money', async () => {
  await expect(getBalance(vi.fn().mockResolvedValue(balance), '12')).resolves.toEqual(balance)
  await expect(listExpenses(vi.fn().mockResolvedValue([{ ...expense, amount: 100 }]), '12'))
    .rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
})
