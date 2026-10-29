import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { AuthProvider, useAuth } from '../auth/AuthContext'
import { TOKEN_KEY } from '../auth/tokenStorage'
import { FinanceSummary } from './FinanceSummary'

const stamp = '2026-09-20T00:00:00Z'
const balance = {
  trip_id: 12, currency: 'USD',
  members: [
    { user_id: 1, username: 'Person1', paid: '100.00', share: '33.34', settled: '0.00', balance: '66.66' },
    { user_id: 2, username: 'Person2', paid: '0.00', share: '33.33', settled: '0.00', balance: '-33.33' },
    { user_id: 3, username: 'Person3', paid: '33.33', share: '33.33', settled: '0.00', balance: '0.00' },
  ],
  suggested_settlements: [{ from_user_id: 2, to_user_id: 1, amount: '33.33' }],
  settlement: { transfers: 1, unsettled_members: 2, minimal: true },
}
const json = (data: unknown) => new Response(JSON.stringify(data))

function Ready({ onOpenBalances }: { onOpenBalances?: () => void }) {
  const { state } = useAuth()
  return state.status === 'authenticated'
    ? <FinanceSummary tripId="12" refreshKey={0} onOpenBalances={onOpenBalances} /> : null
}

function mount(userId: number, body: unknown = balance, onOpenBalances?: () => void) {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => url.endsWith('/me')
    ? json({ id: userId, username: `Person${userId}`, email: `p${userId}@example.com`, created_at: stamp })
    : json(body)))
  sessionStorage.setItem(TOKEN_KEY, 'test-token')
  render(<AuthProvider><Ready onOpenBalances={onOpenBalances} /></AuthProvider>)
}

it('shows what the signed-in member owes, using the server amounts without the minus sign', async () => {
  mount(2)
  const summary = await screen.findByRole('region', { name: 'Your expense summary' })
  expect(within(summary).getByText('You owe')).toBeInTheDocument()
  expect(within(summary).getByText('33.33 USD', { selector: '.summary-headline .summary-amount' })).toBeInTheDocument()
  expect(within(summary).getByText('0.00 USD')).toBeInTheDocument()
  expect(within(summary).getByRole('list', { name: 'Your suggested transfers' })).toHaveTextContent('Pay Person133.33 USD')
  expect(summary).not.toHaveTextContent('-33.33')
})

it('shows money owed to the member and who pays it', async () => {
  mount(1)
  const summary = await screen.findByRole('region', { name: 'Your expense summary' })
  expect(within(summary).getByText("You're owed")).toBeInTheDocument()
  expect(within(summary).getByText('66.66 USD')).toBeInTheDocument()
  expect(within(summary).getByRole('list', { name: 'Your suggested transfers' })).toHaveTextContent('Person2 pays you33.33 USD')
})

it('says when the member is square and links to everyone\'s balances', async () => {
  const onOpenBalances = vi.fn()
  mount(3, balance, onOpenBalances)
  const summary = await screen.findByRole('region', { name: 'Your expense summary' })
  expect(within(summary).getByText("You're all square")).toBeInTheDocument()
  expect(within(summary).queryByRole('list')).not.toBeInTheDocument()
  await userEvent.click(within(summary).getByRole('button', { name: "See everyone's balances" }))
  expect(onOpenBalances).toHaveBeenCalledTimes(1)
})

it('explains the empty state before the first expense', async () => {
  mount(1, {
    ...balance, currency: null, suggested_settlements: [],
    settlement: { transfers: 0, unsettled_members: 0, minimal: true },
    members: balance.members.map((member) => ({ ...member, paid: '0.00', share: '0.00', settled: '0.00', balance: '0.00' })),
  })
  expect(await screen.findByText(/No expenses yet\. Your share and balance appear here/)).toBeInTheDocument()
  expect(screen.queryByRole('region', { name: 'Your expense summary' })).not.toBeInTheDocument()
})
