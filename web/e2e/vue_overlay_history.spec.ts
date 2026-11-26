// CF-1272: an open overlay holds one history entry on the page's address, so Back closes it and
// leaves the page where it was, and an overlay closed any other way leaves no entry behind.

import type { Page } from '@playwright/test'
import { TIMEOUT, card, expect, test } from './fixtures'

const held = (page: Page) =>
  page.evaluate(() => (history.state as Record<string, unknown> | null)?.codeFactoryOverlay ?? null)

test('e2e_back_closes_the_command_menu_and_stays_on_the_page', async ({ writesBoard: page }) => {
  const address = page.url()
  await page.keyboard.press('Meta+k')
  const menu = page.getByRole('dialog', { name: 'Command menu' })
  await expect(menu).toBeVisible()

  await page.goBack()

  await expect(menu).toBeHidden()
  expect(page.url()).toBe(address)
})

test('e2e_back_after_escape_leaves_the_page', async ({ writesBoard: page }) => {
  await page.keyboard.press('Meta+k')
  const menu = page.getByRole('dialog', { name: 'Command menu' })
  await expect(menu).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(menu).toBeHidden()
  await expect.poll(() => held(page)).toBeNull()

  await page.goBack()

  expect(page.url()).toBe('about:blank')
})

test('e2e_the_menus_new_ticket_closes_on_back_and_leaves_the_address', async ({
  writesBoard: page,
}) => {
  const address = page.url()
  await page.keyboard.press('Meta+k')
  const menu = page.getByRole('dialog', { name: 'Command menu' })
  await menu.getByRole('combobox', { name: 'Search commands' }).fill('new ticket')
  await menu.getByRole('option', { name: /^New ticket/ }).click()
  const form = page.getByRole('dialog', { name: 'New ticket', exact: true })
  await expect(form).toBeVisible()
  await expect(menu).toBeHidden()

  await page.goBack()

  await expect(form).toBeHidden()
  expect(page.url()).toBe(address)
  await expect.poll(() => held(page)).toBeNull()
  await page.goBack()
  expect(page.url()).toBe('about:blank')
})

test('e2e_back_closes_the_ticket_panel_and_stays_on_the_board', async ({ writesBoard: page }) => {
  const address = page.url()
  await card(page, 'CF-2').click()
  const panel = page.getByRole('dialog', { name: /CF-2$/ })
  await panel.getByRole('button', { name: 'Delete' }).waitFor({ timeout: TIMEOUT })

  await page.goBack()

  await expect(panel).toBeHidden()
  expect(page.url()).toBe(address)
})

test('e2e_the_menu_archives_the_open_ticket', async ({ served, writesBoard: page }) => {
  await card(page, 'CF-2').click()
  const panel = page.getByRole('dialog', { name: /CF-2$/ })
  await panel.getByRole('button', { name: 'Delete' }).waitFor({ timeout: TIMEOUT })

  await page.keyboard.press('Meta+k')
  const menu = page.getByRole('dialog', { name: 'Command menu' })
  await expect(menu.getByRole('option', { name: /^Archive/ })).toHaveCount(1)
  await menu.getByRole('option', { name: /^Archive/ }).click()

  await expect.poll(() => served.ticket('CF-2')).toContain('archived: true')
})

test('e2e_a_page_chosen_in_the_menu_is_one_back_from_the_board', async ({ writesBoard: page }) => {
  const address = page.url()
  // The second visit finds the page's code loaded, so nothing but history orders the navigation.
  for (const visit of [1, 2]) {
    await page.keyboard.press('Meta+k')
    const menu = page.getByRole('dialog', { name: 'Command menu' })
    await menu.getByRole('combobox', { name: 'Search commands' }).fill('go to inbox')
    await menu.getByRole('option', { name: /^Go to Inbox/ }).click()
    await expect(page, `visit ${String(visit)}`).toHaveURL(/\/inbox$/)

    await page.goBack()

    await expect(page, `back from visit ${String(visit)}`).toHaveURL(address)
  }
})
