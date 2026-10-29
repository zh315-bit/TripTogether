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
  paid_by_user_id: 1, expense_date: '2026-09-20', split_method: 'equal', created_by_user_id: 2,
  created_at: '2026-09-20T00:00:00Z', version: 1, updated_at: '2026-09-20T00:00:00Z',
  splits: [{ user_id: 1, share_amount: '33.34', weight: null }, { user_id: 2, share_amount: '33.33', weight: null },
    { user_id: 3, share_amount: '33.33', weight: null }],
}
const balance = {
  trip_id: 12, currency: 'USD',
  members: [{ user_id: 1, username: 'Person1', paid: '100.00', share: '33.34', settled: '0.00', balance: '66.66' },
    { user_id: 2, username: 'Person2', paid: '0.00', share: '33.33', settled: '0.00', balance: '-33.33' }],
  suggested_settlements: [{ from_user_id: 2, to_user_id: 1, amount: '33.33' }],
  settlement: { transfers: 1, unsettled_members: 2, minimal: true },
}
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status })
const payments: unknown[] = []

function mount(rows: unknown[] = [expense], ledger: unknown = balance) {
  const onChanged = vi.fn()
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith('/me')) return json({ id: 2, username: 'Person2', email: 'p2@example.com', created_at: expense.created_at })
    if (url.endsWith('/members')) return json(members)
    if (url.endsWith('/balances')) return json(ledger)
    if (url.endsWith('/settlements') && !init?.method) return json(payments)
    if (url.endsWith('/settlements') && init?.method === 'POST') {
      return json({ id: 9, trip_id: 12, ...JSON.parse(String(init.body)), note: null, recorded_by_user_id: 2, created_at: expense.created_at }, 201)
    }
    if (init?.method === 'DELETE') return new Response(null, { status: 204 })
    if (init?.method) {
      const sent = JSON.parse(String(init.body)) as Record<string, unknown>
      delete sent.splits
      return json({ ...expense, ...sent, splits: expense.splits })
    }
    return json(rows)
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
  expect(await screen.findByText(/Split equally: Person1 33.34, Person2 33.33, Person3 33.33/)).toBeInTheDocument()
  expect(await screen.findByText('Owes: -33.33 USD')).toBeInTheDocument()
  expect(screen.getByText('Suggested settlements (not payments)')).toBeInTheDocument()
  expect(screen.getByText('1 transfer settles 2 members, the fewest possible.')).toBeInTheDocument()
})

it('shows share weights and exact splits as the server sent them', async () => {
  mount([
    { ...expense, id: 2, description: 'Taxi', split_method: 'shares',
      splits: [{ user_id: 1, share_amount: '66.67', weight: 2 }, { user_id: 2, share_amount: '33.33', weight: 1 }] },
    { ...expense, id: 3, description: 'Tickets', split_method: 'exact',
      splits: [{ user_id: 1, share_amount: '90.00', weight: null }, { user_id: 3, share_amount: '10.00', weight: null }] },
  ], { ...balance, suggested_settlements: [], settlement: { transfers: 5, unsettled_members: 16, minimal: false } })
  expect(await screen.findByText('Split by shares: Person1 ×2 66.67, Person2 ×1 33.33')).toBeInTheDocument()
  expect(screen.getByText('Exact split: Person1 90.00, Person3 10.00')).toBeInTheDocument()
  expect(await screen.findByText(/5 transfers settle 16 members\. The group is too large/)).toBeInTheDocument()
})

it('sends weights for a shares split and rejects non-integer shares', async () => {
  const { fetcher, onChanged } = mount()
  await screen.findByLabelText('Description')
  for (const [label, value] of Object.entries({
    Description: 'Taxi', Amount: '90.00', Currency: 'USD', 'Expense date': '2026-09-20',
  })) fireEvent.change(screen.getByLabelText(label), { target: { value } })
  await userEvent.selectOptions(screen.getByLabelText('Paid by'), '1')
  await userEvent.click(screen.getByLabelText('By shares'))
  await userEvent.click(screen.getByLabelText('Person1'))
  await userEvent.click(screen.getByLabelText('Person2'))
  fireEvent.change(screen.getByLabelText('Person2 shares'), { target: { value: '1.5' } })
  await userEvent.click(screen.getByRole('button', { name: 'Add expense' }))
  expect(screen.getByRole('alert')).toHaveTextContent('whole number')
  fireEvent.change(screen.getByLabelText('Person2 shares'), { target: { value: '3' } })
  await userEvent.click(screen.getByRole('button', { name: 'Add expense' }))
  await waitFor(() => expect(onChanged).toHaveBeenCalledOnce())
  const body = fetcher.mock.calls.find(([, init]) => init?.method === 'POST')?.[1]?.body
  expect(JSON.parse(String(body))).toEqual(expect.objectContaining({
    split_method: 'shares', splits: [{ user_id: 1, weight: 1 }, { user_id: 2, weight: 3 }],
  }))
  expect(JSON.parse(String(body))).not.toHaveProperty('participant_user_ids')
})

it('keeps exact amounts honest before sending them', async () => {
  const { fetcher, onChanged } = mount()
  await screen.findByLabelText('Description')
  for (const [label, value] of Object.entries({
    Description: 'Tickets', Amount: '100.00', Currency: 'USD', 'Expense date': '2026-09-20',
  })) fireEvent.change(screen.getByLabelText(label), { target: { value } })
  await userEvent.selectOptions(screen.getByLabelText('Paid by'), '1')
  await userEvent.click(screen.getByLabelText('Exact amounts'))
  await userEvent.click(screen.getByLabelText('Person1'))
  await userEvent.click(screen.getByLabelText('Person3'))
  fireEvent.change(screen.getByLabelText('Person1 amount'), { target: { value: '90' } })
  expect(screen.getByRole('status')).toHaveTextContent('Assigned 90.00 of 100.00; 10.00 left.')
  fireEvent.change(screen.getByLabelText('Person3 amount'), { target: { value: '10.01' } })
  expect(screen.getByRole('status')).toHaveTextContent('0.01 over')
  await userEvent.click(screen.getByRole('button', { name: 'Add expense' }))
  expect(screen.getByRole('alert')).toHaveTextContent('Exact amounts add up to 100.01, not 100.00.')
  expect(fetcher.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false)
  fireEvent.change(screen.getByLabelText('Person3 amount'), { target: { value: '10' } })
  expect(screen.getByRole('status')).toHaveTextContent('adds up')
  await userEvent.click(screen.getByRole('button', { name: 'Add expense' }))
  await waitFor(() => expect(onChanged).toHaveBeenCalledOnce())
  const body = fetcher.mock.calls.find(([, init]) => init?.method === 'POST')?.[1]?.body
  expect(JSON.parse(String(body))).toEqual(expect.objectContaining({
    split_method: 'exact', splits: [{ user_id: 1, amount: '90.00' }, { user_id: 3, amount: '10.00' }],
  }))
})

it('opens an existing shares expense with its weights filled in', async () => {
  mount([{ ...expense, split_method: 'shares',
    splits: [{ user_id: 1, share_amount: '25.00', weight: 1 }, { user_id: 2, share_amount: '75.00', weight: 3 }] }])
  await userEvent.click(await screen.findByRole('button', { name: 'Edit expense' }))
  expect(screen.getByLabelText('By shares')).toBeChecked()
  expect(screen.getByLabelText('Person2 shares')).toHaveValue('3')
  expect(screen.queryByLabelText('Person3 shares')).not.toBeInTheDocument()
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

it('records a suggested transfer as paid and reloads the balances', async () => {
  const { fetcher } = mount()
  await userEvent.click(await screen.findByRole('button', { name: /Mark 33.33 USD from Person2 to Person1 as paid/ }))
  const post = fetcher.mock.calls.find(([url, init]) => String(url).endsWith('/settlements') && init?.method === 'POST')
  expect(JSON.parse(String(post?.[1]?.body))).toMatchObject({
    from_user_id: 2, to_user_id: 1, amount: '33.33', currency: 'USD',
  })
  expect(JSON.parse(String(post?.[1]?.body)).paid_on).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  await waitFor(() => expect(fetcher.mock.calls.filter(([url]) => String(url).endsWith('/balances')).length).toBeGreaterThanOrEqual(2))
})
