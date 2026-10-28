import { expect, test } from '@playwright/test'
import { addMember, createTrip, openPanel, registerUser, signedInPage } from './support'

test.describe('two members in the same trip', () => {
  test('see each other\'s itinerary changes within a second, and a stale edit is refused', async ({ browser, request }) => {
    const mika = await registerUser(request, 'Mika')
    const jonas = await registerUser(request, 'Jonas')
    const trip = await createTrip(request, mika)
    await addMember(request, mika, trip, jonas)

    const mikaPage = await signedInPage(browser, mika)
    const jonasPage = await signedInPage(browser, jonas)
    await openPanel(mikaPage, trip.id, 'itinerary')
    await openPanel(jonasPage, trip.id, 'itinerary')

    // Mika adds an item; Jonas's list updates in place with a notice saying who did it.
    await mikaPage.getByLabel('Title').fill('Temple visit')
    await mikaPage.getByRole('button', { name: 'Add item' }).click()
    await expect(jonasPage.getByRole('article').filter({ hasText: 'Temple visit' })).toBeVisible()
    await expect(jonasPage.getByRole('status').filter({ hasText: `${mika.username} added an itinerary item.` })).toBeVisible()
    // Mika's own change produces no notice on Mika's screen.
    await expect(mikaPage.getByRole('status').filter({ hasText: /added an itinerary item/ })).toHaveCount(0)

    // Both open the editor. Jonas saves first; Mika's save carries the old version.
    await mikaPage.getByRole('button', { name: 'Edit', exact: true }).click()
    await jonasPage.getByRole('button', { name: 'Edit', exact: true }).click()
    await jonasPage.getByLabel('Title').fill('Temple at dawn')
    await jonasPage.getByRole('button', { name: 'Save item' }).click()
    await expect(jonasPage.getByRole('article').filter({ hasText: 'Temple at dawn' })).toBeVisible()

    await mikaPage.getByLabel('Title').fill('Temple at noon')
    await mikaPage.getByRole('button', { name: 'Save item' }).click()
    await expect(mikaPage.getByText(/changed by another member while you were editing/)).toBeVisible()
    await expect(mikaPage.getByRole('article').filter({ hasText: 'Temple at dawn' })).toBeVisible()
    await expect(mikaPage.getByText('Temple at noon')).toHaveCount(0)
    await expect(jonasPage.getByText('Temple at noon')).toHaveCount(0)

    await mikaPage.context().close()
    await jonasPage.context().close()
  })
})
