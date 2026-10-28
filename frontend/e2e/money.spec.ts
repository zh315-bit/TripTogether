import { expect, test, type Page } from '@playwright/test'
import { addMember, api, createTrip, openPanel, registerUser, signedInPage, type Trip, type User } from './support'

async function fillExpense(page: Page, payer: User, description: string, amount: string) {
  await page.getByLabel('Description').fill(description)
  await page.getByLabel('Amount', { exact: true }).fill(amount)
  await page.getByLabel('Currency').fill('USD')
  await page.getByLabel('Expense date').fill('2027-06-10')
  await page.getByLabel('Paid by').selectOption({ label: payer.username })
}

test('splits by shares through the form and shows the settlement', async ({ browser, request }) => {
  const mika = await registerUser(request, 'Mika')
  const jonas = await registerUser(request, 'Jonas')
  const trip = await createTrip(request, mika)
  await addMember(request, mika, trip, jonas)
  const page = await signedInPage(browser, mika)
  await openPanel(page, trip.id, 'expenses')

  await fillExpense(page, mika, 'Ryokan night', '90.00')
  await page.getByLabel('By shares').check()
  await page.getByLabel(mika.username, { exact: true }).check()
  await page.getByLabel(jonas.username, { exact: true }).check()
  await page.getByLabel(`${jonas.username} shares`).fill('2')
  await page.getByRole('button', { name: 'Add expense' }).click()
  await expect(page.getByText(`Split by shares: ${mika.username} ×1 30.00, ${jonas.username} ×2 60.00`)).toBeVisible()

  // Exact amounts are checked before anything is sent.
  await fillExpense(page, mika, 'Tickets', '100.00')
  await page.getByLabel('Exact amounts').check()
  await page.getByLabel(mika.username, { exact: true }).check()
  await page.getByLabel(`${mika.username} amount`).fill('90')
  await expect(page.getByText('Assigned 90.00 of 100.00; 10.00 left.')).toBeVisible()
  await page.getByRole('button', { name: 'Add expense' }).click()
  await expect(page.getByRole('alert')).toHaveText('Exact amounts add up to 90.00, not 100.00.')

  await page.getByRole('tab', { name: 'Balances' }).click()
  await expect(page.getByText('1 transfer settles 2 members, the fewest possible.')).toBeVisible()
  await expect(page.locator('.settlement-row')).toHaveText([new RegExp(`${jonas.username} → ${mika.username}.*60\\.00 USD`)])
  await page.context().close()
})

test('five members settle in three transfers, not four', async ({ browser, request }) => {
  const [mika, jonas, aiko, ben, chen] = await Promise.all(
    ['Mika', 'Jonas', 'Aiko', 'Ben', 'Chen'].map((name) => registerUser(request, name)))
  const trip: Trip = await createTrip(request, mika)
  for (const member of [jonas, aiko, ben, chen]) await addMember(request, mika, trip, member)
  // Balances: Mika +60, Jonas +50, Aiko -30, Ben -30, Chen -50. Greedy pairing needs four
  // transfers; the zero-sum groups {Mika, Aiko, Ben} and {Jonas, Chen} need three.
  await api(request, mika.token, 'POST', `/trips/${trip.id}/expenses`, {
    description: 'Ryokan night', amount: '90.00', currency: 'USD', expense_date: '2027-06-10',
    paid_by_user_id: mika.id, split_method: 'shares',
    splits: [{ user_id: mika.id, weight: 1 }, { user_id: jonas.id, weight: 2 }],
  })
  await api(request, jonas.token, 'POST', `/trips/${trip.id}/expenses`, {
    description: 'Kaiseki dinner', amount: '110.00', currency: 'USD', expense_date: '2027-06-11',
    paid_by_user_id: jonas.id, split_method: 'exact',
    splits: [{ user_id: chen.id, amount: '50.00' }, { user_id: aiko.id, amount: '30.00' }, { user_id: ben.id, amount: '30.00' }],
  })

  const page = await signedInPage(browser, chen)
  await openPanel(page, trip.id, 'balances')
  await expect(page.getByText('3 transfers settle 5 members, the fewest possible.')).toBeVisible()
  // Group order follows user ids, which registration hands out in any order.
  const rows = page.locator('.settlement-row')
  await expect(rows).toHaveCount(3)
  const texts = (await rows.allTextContents()).map((text) => text.replace(/Mark as paid/g, '').replace(/\s*—\s*/g, ' — ').replace(/\s+/g, ' ').trim()).sort()
  expect(texts).toEqual([
    `${aiko.username} → ${mika.username} — 30.00 USD`,
    `${ben.username} → ${mika.username} — 30.00 USD`,
    `${chen.username} → ${jonas.username} — 50.00 USD`,
  ].sort())
  await expect(page.getByText('Owes: -50.00 USD')).toBeVisible()
  await page.context().close()
})
