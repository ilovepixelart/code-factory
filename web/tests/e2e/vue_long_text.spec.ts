// CF-1292 acceptance flows: long unbroken text (a hash, an id, a long branch) never overflows its
// box and is never cut without a way to read it, on the board card, the ticket panel and page, the
// ticket list, the Flow table, the Team rows, the Sessions row and the Agents page, at 1440 and 390 px in both
// themes, served by the server over the writes sample without the run follower.

import { TIMEOUT, card, expect, toasts, useTheme } from './fixtures'
import {
  frame,
  problems,
  showTicket,
  sourceAboveFooter,
  stackedProperties,
  type View,
} from './long_text_checks'
import { PAGE_RAIL, PANEL_RAIL, PULL, THEMES, WIDE, longAgents, test } from './long_text_fixture'

test('e2e_a_long_token_stays_inside_the_board_card', async ({ served, page }) => {
  const found = await problems(
    page,
    async () => {
      await page.goto(`${served.url}/tickets`)
      await card(page, 'CF-90').waitFor({ timeout: TIMEOUT })
    },
    () => card(page, 'CF-90'),
  )

  expect(found).toStrictEqual([])
})

test('e2e_a_long_token_stays_inside_the_ticket_list', async ({ served, page }) => {
  const found = await problems(
    page,
    async () => {
      await page.goto(`${served.url}/tickets/list`)
      await page.getByRole('row').filter({ hasText: 'CF-90' }).waitFor({ timeout: TIMEOUT })
    },
    () => page.getByRole('table'),
  )

  expect(found).toStrictEqual([])
})

// The panel is the board's side sheet; the page has the properties as a rail beside the content.
for (const view of ['panel', 'page'] as View[]) {
  test(`e2e_a_long_token_stays_inside_the_ticket_${view}`, async ({ served, page }) => {
    const found = await problems(
      page,
      () => showTicket(page, served, view),
      () => frame(page, view),
      () => sourceAboveFooter(page, view),
    )

    expect(found).toStrictEqual([])
  })
}

// The property column beside the content, in the panel at 1600 px and on the page at 1492 px.
for (const [view, size] of [
  ['panel', PANEL_RAIL],
  ['page', PAGE_RAIL],
] as const) {
  test(`e2e_a_property_value_takes_at_most_two_lines_in_the_${view}_rail`, async ({
    served,
    page,
  }) => {
    await page.setViewportSize(size)
    await showTicket(page, served, view)
    const rail = frame(page, view).getByRole('complementary', { name: 'Properties' })
    expect((await rail.boundingBox())?.width).toBeLessThan(300)

    for (const theme of THEMES) {
      await useTheme(page, theme)
      expect(await stackedProperties(page, view), theme).toStrictEqual([])
    }
    await expect(page.getByTestId('source')).toHaveAttribute('title', /^automation:main-failed@/)
  })
}

test('e2e_a_pull_request_address_in_activity_is_a_short_link', async ({ served, page }) => {
  await page.setViewportSize(WIDE)
  await page.goto(`${served.url}/tickets/sample/CF-90`)
  const log = page.getByRole('list', { name: 'Activity' })
  await log.waitFor({ timeout: TIMEOUT })

  const opened = log.getByRole('listitem').filter({ hasText: 'Pull request opened (#1185)' })
  const merged = log.getByRole('listitem').filter({ hasText: 'Pull request merged (#1185)' })
  await expect(opened.getByRole('link', { name: '#1185' })).toHaveAttribute('href', PULL)
  await expect(opened.getByRole('link', { name: '#1185' })).toHaveAttribute('target', '_blank')
  await expect(merged.getByRole('link', { name: '#1185' })).toHaveAttribute('href', PULL)
  await expect(log).not.toContainText(PULL)
  // An address that is no pull request on GitHub stays the text it is.
  await expect(log).toContainText('https://example.test/pull/9')
  await expect(log.getByRole('link', { name: 'https://example.test/pull/9' })).toHaveCount(0)
})

test('e2e_a_long_token_stays_inside_the_flow_table', async ({ served, page }) => {
  const recent = page.getByRole('region', { name: /^Recently merged/ })
  const found = await problems(
    page,
    async () => {
      await page.goto(`${served.url}/flow`)
      await recent.getByRole('row').filter({ hasText: 'CF-91' }).waitFor({ timeout: TIMEOUT })
    },
    () => recent,
  )

  expect(found).toStrictEqual([])
})

test('e2e_a_long_token_stays_inside_the_team_rows', async ({ served, page }) => {
  const found = await problems(
    page,
    async () => {
      await page.goto(`${served.url}/team`)
      await page
        .getByRole('region', { name: /^Done today/ })
        .getByRole('listitem')
        .filter({ hasText: 'CF-91' })
        .waitFor({ timeout: TIMEOUT })
    },
    () => page.getByRole('main'),
  )

  expect(found).toStrictEqual([])
})

test('e2e_the_team_title_takes_the_free_width_before_it_is_cut', async ({ served, page }) => {
  await page.setViewportSize(WIDE)
  await page.goto(`${served.url}/team`)
  const row = page
    .getByRole('region', { name: /^Done today/ })
    .getByRole('listitem')
    .filter({ hasText: 'CF-91' })
  await row.waitFor({ timeout: TIMEOUT })

  const widths = await row.evaluate((e) =>
    [...e.children].map((cell) => cell.getBoundingClientRect().width),
  )

  // The title and the line of what the row does share what the fixed columns leave: the title,
  // the one that is cut on a hash, takes the larger part.
  const [, , title = 0, , line = 1] = widths
  expect(title / (title + line)).toBeGreaterThanOrEqual(0.59)
})

test('e2e_a_long_token_stays_inside_the_session_row', async ({ served, page }) => {
  const row = page.getByRole('listitem').filter({ hasText: 'Tool call and subagents' })
  const found = await problems(
    page,
    async () => {
      await page.goto(served.url)
      await row.waitFor({ timeout: TIMEOUT })
      await row.getByText('Tool call and subagents').click()
    },
    () => row,
  )

  expect(found).toStrictEqual([])
})

test('e2e_a_long_refusal_wraps_inside_the_error_toast', async ({ served, page }) => {
  const reason = `cannot stop: ${'a'.repeat(300)}`
  await page.route('**/api/agents/stop', (route) =>
    route.fulfill({
      status: 409,
      contentType: 'application/json',
      body: JSON.stringify({ error: reason }),
    }),
  )
  await page.goto(`${served.url}/team`)
  await page.keyboard.press('ControlOrMeta+k')
  await page.getByRole('combobox', { name: 'Search commands' }).fill('stop every')
  await page.keyboard.press('Enter')

  const toast = toasts(page).getByText('cannot stop:')
  await expect(toast).toBeVisible({ timeout: TIMEOUT })
  const alert = toasts(page).getByRole('listitem').filter({ has: toast })
  const [scroll, client] = await alert.evaluate((e) => [e.scrollWidth, e.clientWidth])

  expect(scroll).toBeLessThanOrEqual(client)
})

for (const [tab, region] of [
  ['', 'agents'],
  ['?tab=connections', 'connections'],
] as const) {
  test(`e2e_long_names_stay_inside_the_${region}_tab`, async ({ served, page }) => {
    longAgents(served)
    const found = await problems(
      page,
      async () => {
        await page.goto(`${served.url}/agents${tab}`)
        await page
          .getByRole('region', { name: new RegExp(`^${region}`, 'i') })
          .getByRole('listitem')
          .waitFor({ timeout: TIMEOUT })
      },
      () => page.getByRole('main'),
    )

    expect(found).toStrictEqual([])
  })
}

test('e2e_a_ticket_title_keeps_a_readable_width_in_the_list_on_a_phone', async ({
  served,
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(`${served.url}/tickets/list`)
  const row = page.getByRole('row').filter({ hasText: 'CF-90' })
  await row.waitFor({ timeout: TIMEOUT })
  const title = await row.getByRole('cell', { name: /Main fails web-unused/ }).boundingBox()

  expect(title?.width).toBeGreaterThanOrEqual(180)
})
