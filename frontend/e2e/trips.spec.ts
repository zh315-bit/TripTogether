import { expect, test } from '@playwright/test'
import { registerUser, signedInPage, unique } from './support'

test('a new user registers, creates a trip and brings a friend in', async ({ page, browser, request }) => {
  const friend = await registerUser(request, 'Friend')
  const username = unique('Owner')
  const password = `Pw-${unique('a')}-${unique('b')}`

  await page.goto('/register')
  await page.getByLabel('Username').fill(username)
  await page.getByLabel('Email').fill(`${username.toLowerCase()}@example.com`)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Create account' }).click()
  // Registration hands over to the login page rather than signing in silently.
  await expect(page).toHaveURL(/\/login$/)
  await page.getByLabel('Email').fill(`${username.toLowerCase()}@example.com`)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Log in' }).click()
  await expect(page).toHaveURL(/\/trips$/)

  // The empty dashboard offers the trip form directly.
  const tripName = unique('Kyoto')
  await page.getByLabel('Trip name').fill(tripName)
  await page.getByLabel('Destination').fill('Kyoto, Japan')
  await page.getByLabel('Start date').fill('2027-06-10')
  await page.getByLabel('End date').fill('2027-06-12')
  await page.getByRole('button', { name: 'Create trip' }).click()
  await expect(page).toHaveURL(/\/trips\/\d+/)
  await expect(page.getByRole('combobox', { name: 'Current trip' })).toContainText(tripName)
  const tripId = Number(new URL(page.url()).pathname.split('/').pop())

  await page.getByRole('tab', { name: 'Members' }).click()
  await page.getByLabel('Invite a registered user').fill(friend.email)
  await page.getByRole('button', { name: 'Send invite' }).click()

  // The friend accepts from their own inbox and lands in the same trip.
  const friendPage = await signedInPage(browser, friend)
  await friendPage.goto('/trips')
  await friendPage.getByRole('button', { name: /Invitations, 1 pending/ }).click()
  // With no trips yet the dashboard also shows the inbox inline; act in the popover.
  const inbox = friendPage.getByRole('dialog')
  await inbox.getByRole('button', { name: 'Accept' }).click()
  await expect(inbox.getByText('accepted')).toBeVisible()

  // The owner's member list updated live, with a notice that clears itself after a few seconds.
  await expect(page.getByRole('status').filter({ hasText: `${friend.username} joined the trip.` })).toBeVisible()
  await expect(page.getByText(friend.email)).toBeVisible()

  await friendPage.goto(`/trips/${tripId}?panel=members`)
  await expect(friendPage.getByText(username).first()).toBeVisible()
  await expect(friendPage.getByText(friend.username).first()).toBeVisible()
  await friendPage.context().close()
})
