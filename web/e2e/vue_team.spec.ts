// The sidebar opens Team and its tables keep the detail panel reachable by keyboard.

import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import type { Page } from '@playwright/test'
import { TIMEOUT, dropSample, expect, prepareSample, start, test as base } from './fixtures'

const test = base.extend<object, { teamUrl: string }>({
  teamUrl: [
    async ({}, use) => {
      const state = mkdtempSync(join(tmpdir(), 'cf-team-demo-'))
      const env = { CODE_FACTORY_STATE_DIR: state }
      const schema = prepareSample('demo', env)
      try {
        const { url, stop } = await start(schema, { env })
        try {
          await use(url)
        } finally {
          stop()
        }
      } finally {
        dropSample(schema)
        rmSync(state, { recursive: true, force: true })
      }
    },
    { scope: 'worker', timeout: 90_000 },
  ],
})

test('e2e_the_sidebar_opens_the_team_page', async ({ teamUrl, page }) => {
  await page.goto(`${teamUrl}/tickets`)

  await page.getByRole('link', { name: 'Team' }).click()

  await expect(page).toHaveURL(`${teamUrl}/team`)
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Team')
})

/** The ticket button for the sample's open question and the title that names its peek. */
async function firstRow(page: Page) {
  const row = page
    .getByRole('table', { name: 'Waiting on you', exact: true })
    .getByRole('button', { name: 'Gift cards', exact: true })
  await expect(row).toBeVisible({ timeout: TIMEOUT })
  const title = (await row.innerText()).trim()
  return { row, title }
}

/** Whether the focused element is inside an element matching `selector`. */
const focusIn = (page: Page, selector: string) =>
  page.evaluate((sel) => document.activeElement?.closest(sel) !== null, selector)

test('team_peek_sheet_holds_focus_and_returns_it', async ({ teamUrl, page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(`${teamUrl}/team`)
  const { row, title } = await firstRow(page)
  await row.focus()

  await page.keyboard.press('Enter')

  await expect(page.getByRole('dialog', { name: title })).toBeVisible()
  await expect(page.getByRole('dialog', { name: title })).toHaveAttribute('aria-modal', 'true')
  expect(await focusIn(page, '[aria-modal="true"]')).toBe(true)
  for (let i = 0; i < 12; i++) {
    await page.keyboard.press('Tab')
    expect(await focusIn(page, '[aria-modal="true"]')).toBe(true)
  }
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog', { name: title })).toHaveCount(0)
  await expect(row).toBeFocused()

  await page.keyboard.press('Enter')
  await page.getByRole('dialog', { name: title }).getByRole('button', { name: 'Close' }).click()
  await expect(page.getByRole('dialog', { name: title })).toHaveCount(0)
  await expect(row).toBeFocused()
})

test('team_peek_beside_the_list_keeps_focus_on_the_row', async ({ teamUrl, page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.goto(`${teamUrl}/team`)
  const { row, title } = await firstRow(page)
  await row.focus()

  await page.keyboard.press('Enter')

  await expect(page.getByRole('complementary', { name: title })).toBeVisible()
  await expect(page.getByRole('dialog', { name: title })).toHaveCount(0)
  await expect(row).toBeFocused()
})

test('team_escape_closes_only_the_command_menu_over_a_peek', async ({ teamUrl, page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.goto(`${teamUrl}/team`)
  const { row, title } = await firstRow(page)
  await row.click()
  const peek = page.getByRole('complementary', { name: title })
  await expect(peek).toBeVisible()

  await page.keyboard.press('Control+k')
  await expect(page.getByRole('dialog')).toHaveCount(1)
  await page.keyboard.press('Escape')

  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(peek).toBeVisible()
})
