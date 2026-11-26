// CF-209 acceptance flows: the sessions board and a session's page in the Vue app, served by the
// server over the api sample state.

import type { Locator, Page } from '@playwright/test'
import { TIMEOUT, expect, header, test as base } from './fixtures'

const test = base.extend<{ page: Page; sessionsUrl: string }>({
  sessionsUrl: async ({ api }, use) => use(api.url),
  page: async ({ browser }, use) => {
    const context = await browser.newContext()
    const opened = await context.newPage()
    await use(opened)
    await context.close()
  },
})

/** The session row a person knows by its short id. */
function session(scope: Page | Locator, id: string): Locator {
  const page = 'goto' in scope ? scope : scope.page()
  return scope.getByRole('listitem').filter({ has: page.getByText(id, { exact: true }) })
}

test('e2e_the_sessions_board_lists_sessions', async ({ sessionsUrl, page }) => {
  await page.goto(sessionsUrl)
  const waiting = page.getByRole('list', { name: 'Waiting on you' })
  await session(waiting, 's-block').waitFor({ timeout: TIMEOUT })
  await expect(session(waiting, 's-work')).toHaveCount(0)
  await expect(session(page, 's-work')).toContainText('$1.50 incomplete · 1.5k out')
  await expect(session(page, 's-end')).toHaveCount(0)
  await page.getByRole('switch', { name: 'Show ended' }).check()
  await session(page, 's-end').waitFor({ timeout: TIMEOUT })
})

test('e2e_a_session_page_shows_its_turns', async ({ sessionsUrl, page }) => {
  await page.goto(sessionsUrl)
  await page.getByRole('link', { name: 'Session s-idle' }).click()
  const timeline = page.getByRole('list', { name: 'Timeline' })
  await timeline.waitFor({ timeout: TIMEOUT })
  const facts = await page.getByRole('region', { name: 'Session' }).innerText()
  const turns = timeline.getByRole('listitem').filter({ has: page.getByText(/^Turn \d+$/) })
  await expect(turns).not.toHaveCount(0)
  const labels = await turns.getByText(/^Turn \d+$/).allTextContents()
  const latest = turns.filter({ has: page.getByText(labels.at(-1) ?? '', { exact: true }) })

  expect(page.url().endsWith('/sessions/s-idle')).toBe(true)
  expect(facts).toContain('s-idle')
  await expect(latest.getByRole('button', { expanded: true })).toHaveCount(1)
  await expect(header(page).getByRole('link', { name: 'Sessions' })).toBeVisible()
})

test('e2e_the_state_tabs_fit_their_labels_on_a_phone', async ({ sessionsUrl, page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(sessionsUrl)
  const tabs = page.getByRole('navigation', { name: 'Filter by state' }).getByRole('tab')
  await expect(tabs).toHaveCount(5, { timeout: TIMEOUT })

  const squashed = await tabs.evaluateAll((links) =>
    links.filter((a) => a.scrollWidth > a.clientWidth).map((a) => a.textContent),
  )
  expect(squashed).toStrictEqual([])
})

const TABS = { name: 'Filter by state' }

test('e2e_the_state_tabs_are_44px_tall_on_touch', async ({ sessionsUrl, browser }) => {
  const context = await browser.newContext({
    hasTouch: true,
    isMobile: true,
    viewport: { width: 390, height: 844 },
  })
  const page = await context.newPage()
  await page.goto(sessionsUrl)
  const tabs = page.getByRole('navigation', TABS).getByRole('tab')
  await expect(tabs).toHaveCount(5, { timeout: TIMEOUT })
  const heights = await tabs.evaluateAll((all) => all.map((a) => a.getBoundingClientRect().height))
  await context.close()

  expect(Math.min(...heights)).toBeGreaterThanOrEqual(44)
})

test('e2e_the_state_tabs_keep_their_height_on_a_fine_pointer', async ({ sessionsUrl, page }) => {
  await page.goto(sessionsUrl)
  const tabs = page.getByRole('navigation', TABS).getByRole('tab')
  await expect(tabs).toHaveCount(5, { timeout: TIMEOUT })
  const heights = await tabs.evaluateAll((all) => all.map((a) => a.getBoundingClientRect().height))

  expect(new Set(heights)).toStrictEqual(new Set([26]))
})
