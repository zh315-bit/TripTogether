import { expect, test } from '@playwright/test'

test('a visitor tries the demo and opens a second window as Jonas', async ({ page, context }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Try the demo' }).click()
  await expect(page).toHaveURL(/\/trips\/\d+$/)
  await expect(page.getByRole('combobox', { name: 'Current trip' })).toContainText('Kyoto long weekend')
  await expect(page.getByText('Demo as Mika')).toBeVisible()

  const [jonasPage] = await Promise.all([
    context.waitForEvent('page'),
    page.getByRole('link', { name: 'Open as Jonas ↗' }).click(),
  ])
  await expect(jonasPage).toHaveURL(page.url())
  await expect(jonasPage.getByRole('status').filter({ hasText: /^Live$/ })).toBeVisible()
  await expect(jonasPage.getByText('Demo as Jonas')).toBeVisible()

  // The seeded trip is a real one: a change in one window shows in the other.
  await jonasPage.goto(`${page.url()}?panel=itinerary`)
  await jonasPage.getByLabel('Title').fill('Matcha break')
  await jonasPage.getByRole('button', { name: 'Add item' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'jonas_demo added an itinerary item.' })).toBeVisible()
  await page.getByRole('tab', { name: 'Balances' }).click()
  await expect(page.getByText(/transfers settle 3 members, the fewest possible/)).toBeVisible()
})
