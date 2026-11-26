// CF-207 acceptance flows: the Vue board, served by the server, over the api sample state.

import { readFileSync, rmSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import type { Page } from '@playwright/test'
import { STAGE_LABELS, STAGES } from '../../src/lib/board'
import { TIMEOUT, box, card, cards, expect, sidebar, test, boardLoaded } from './fixtures'

function column(page: Page, label: string) {
  return page.getByRole('region', { name: label, exact: true })
}

test('e2e_the_vue_board_shows_every_card_value', async ({ api: served, page }) => {
  await page.goto(`${served.url}/tickets`)
  const frd = column(page, 'Spec')
  // CF-2 has a branch, so it is in Build.
  const bug = card(column(page, 'Build'), 'CF-2')
  await bug.waitFor({ timeout: TIMEOUT })
  const text = await bug.innerText()

  await expect(page.getByRole('heading', { name: 'Tickets', level: 1 })).toBeVisible()
  // BRD's limit of 1 and FRD's of 3 fold into Spec's, the smaller; Spec holds the four cards
  // with no branch.
  await expect(column(page, 'Spec').getByRole('heading', { level: 2 })).toContainText('4/1')
  for (const value of [
    'CF-2',
    '↑ CF-1',
    'bug',
    'high',
    'A bug in flight',
    'Blocked waiting on design',
    'ui',
    'agents',
    'Checks passed',
    'PR #2',
    'Approved',
    '$4.25 of $2.50',
    'agent · Build · iteration 2 of 8',
    'sample',
    'feat/CF-2',
    'AL',
  ]) {
    expect(text, value).toContain(value)
  }
  // CF-1021: CF-1 holds documents only, so it is queued and CF-2 is not over the limit.
  expect(text).not.toContain('over the WIP limit')
  const first = await card(frd, 'CF-1').innerText()
  const expectedFirst = ['3 open questions', 'Stopped: agent failed (exit 1)', '1/3', '0/2']
  expect(expectedFirst.filter((value) => !first.includes(value))).toStrictEqual([])
  await expect(card(column(page, 'Spec'), 'CF-3')).toContainText('Blocked by CF-2')
  await expect(page.getByRole('main')).toContainText('Ticket problems')
  await expect(card(frd, 'AB-2', 'second')).toContainText('checks failed')
})

test('e2e_view_settings_in_the_address_narrow_the_board', async ({ api: served, page }) => {
  await page.goto(`${served.url}/tickets?type=bug`)
  await card(page, 'CF-2').waitFor({ timeout: TIMEOUT })
  await expect(cards(page)).toHaveCount(1)
  await expect(page.getByLabel('Active filters').getByText('type: bug')).toBeVisible()

  await page.goto(`${served.url}/tickets?lanes=repository`)
  await card(page, 'CF-2').waitFor({ timeout: TIMEOUT })
  await expect(column(page, 'Spec').getByRole('heading', { level: 3 })).toHaveText([
    /^sample\s*\d+$/,
    /^second\s*\d+$/,
  ])

  await page.goto(`${served.url}/tickets/list?sort=title&dir=desc`)
  const titleLinks = page
    .getByRole('row')
    .filter({ has: page.getByRole('cell') })
    .getByRole('link')
  await expect(titleLinks).not.toHaveCount(0, { timeout: TIMEOUT })
  const titles = await titleLinks.allTextContents()
  const sorted = [...titles].sort((a, b) => {
    const [x, y] = [a.toLowerCase(), b.toLowerCase()]
    return x < y ? 1 : x > y ? -1 : 0
  })
  await expect(titleLinks).toHaveText(sorted)

  await page.goto(`${served.url}/tickets?q=main`)
  await card(page, 'CF-3').waitFor({ timeout: TIMEOUT })
  await expect(cards(page)).toHaveCount(1)
})

test('e2e_columns_fold_and_the_board_pans', async ({ api: served, page }) => {
  await page.setViewportSize({ width: 900, height: 700 })
  await page.goto(`${served.url}/tickets`)
  const review = column(page, 'Review')
  await review.waitFor({ timeout: TIMEOUT })
  await expect(review).toHaveAttribute('data-collapsed')

  await review.getByRole('button', { name: 'Review', exact: true }).click()
  await expect(review).not.toHaveAttribute('data-collapsed')
  await page.reload()
  await boardLoaded(page)
  await expect(column(page, 'Review')).not.toHaveAttribute('data-collapsed')

  const spec = column(page, 'Spec')
  const { x, y, width, height } = await box(spec)
  // The gap between two columns is the board itself, away from any card.
  await page.mouse.move(x + width + 6, y + height / 2)
  await page.mouse.down()
  await page.mouse.move(x + 10, y + height / 2, { steps: 5 })
  await page.mouse.up()
  await expect.poll(async () => (await box(spec)).x).toBeLessThan(x)
})

test('e2e_the_keyboard_reaches_the_command_menu_and_shortcuts', async ({ api: served, page }) => {
  await page.goto(`${served.url}/tickets`)
  await card(page, 'CF-2').waitFor({ timeout: TIMEOUT })

  await page.keyboard.press('Meta+k')
  const menu = page.getByRole('dialog', { name: 'Command menu' })
  await menu.getByRole('combobox', { name: 'Search commands' }).fill('CF-2')
  await expect(menu.getByRole('option').filter({ hasText: 'A bug in flight' })).not.toHaveCount(0)
  await page.keyboard.press('Enter')
  await page.waitForURL(/\/tickets\/sample\/CF-2$/)

  await page.goto(`${served.url}/tickets`)
  await boardLoaded(page)
  await page.keyboard.press('?')
  const shortcuts = page.getByRole('dialog', { name: 'Keyboard shortcuts' })
  await expect(shortcuts).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(shortcuts).toBeHidden()
  await page.keyboard.press('/')
  await expect(page.getByLabel('Filter cards')).toBeFocused()
  await page.getByRole('heading', { name: 'Tickets', level: 1 }).click()
  await page.keyboard.press('[')
  await expect(sidebar(page)).toHaveAttribute('data-state', 'collapsed')
  await page.keyboard.press('g')
  await page.keyboard.press('s')
  await page.waitForURL(/\/sessions$|\/$/)
})

test('e2e_the_board_follows_changes', async ({ api: served, page }) => {
  await page.goto(`${served.url}/tickets`)
  const worked = card(page, 'CF-3')
  await worked.waitFor({ timeout: TIMEOUT })
  const path = join(served.root, '.code-factory', 'tickets', 'CF-3', 'ticket.md')
  const original = readFileSync(path, 'utf8')
  try {
    writeFileSync(path, original.replace('title: Worked on main', 'title: Renamed on disk'))
    await expect(worked.getByText('Renamed on disk')).toBeVisible({ timeout: TIMEOUT })
  } finally {
    writeFileSync(path, original)
  }
})

// The board theme's warning colour per theme (styles/theme.css), as the browser reports it.
const WARNING = { light: 'rgb(180, 83, 9)', dark: 'rgb(251, 191, 36)' } as const

for (const theme of ['light', 'dark'] as const) {
  test(`e2e_the_vue_board_draws_the_board_theme_colours[${theme}]`, async ({
    api: served,
    browser,
  }) => {
    const context = await browser.newContext({ colorScheme: theme })
    const page = await context.newPage()
    await page.goto(`${served.url}/tickets`)
    const age = card(page, 'CF-3').getByText(/^\d+d here$/)
    await age.waitFor({ timeout: TIMEOUT })

    expect(await age.evaluate((el) => getComputedStyle(el).color)).toBe(WARNING[theme])
    await context.close()
  })
}

// CF-494: at the columns' narrowest, the widest count beside it, every description shows whole.
test('e2e_every_column_description_shows_whole', async ({ api: served, page }) => {
  await page.goto(`${served.url}/tickets`)
  await boardLoaded(page)
  const label = new RegExp(`^(${Object.values(STAGE_LABELS).join('|')})$`)
  const folded = page.getByRole('main').getByRole('button', { name: label, expanded: false })
  // Last first: opening a column drops it from `folded`, which would shift the ones after it.
  for (const fold of (await folded.all()).reverse()) await fold.click()
  await expect(folded).toHaveCount(0)
  const headers = page.getByRole('region', { name: label }).getByRole('heading', { level: 2 })
  await expect(headers).toHaveCount(STAGES.length)
  // The description is the header's text that truncates; it has no role of its own.
  const cut = await headers.evaluateAll((all) =>
    all
      .map(
        (h) =>
          [...h.querySelectorAll(':scope > span')].find(
            (span) => getComputedStyle(span).textOverflow === 'ellipsis',
          ) ?? null,
      )
      .filter((hint) => hint === null || hint.scrollWidth > hint.clientWidth)
      .map((hint) => (hint ? `${hint.textContent} (${String(hint.clientWidth)}px)` : 'none')),
  )

  expect(cut).toStrictEqual([])
})

test('e2e_a_cards_menu_button_is_drawn_beside_its_priority_on_touch', async ({
  api: served,
  browser,
}) => {
  const context = await browser.newContext({
    hasTouch: true,
    isMobile: true,
    viewport: { width: 390, height: 844 },
  })
  const page = await context.newPage()
  await page.goto(`${served.url}/tickets`)
  const bug = card(page, 'CF-2')
  await bug.waitFor({ timeout: TIMEOUT })
  const trigger = bug.getByLabel('Actions for CF-2', { exact: true }).filter({ visible: true })
  const priority = bug.getByText('high', { exact: true })
  const [button, label] = [await box(trigger), await box(priority)]
  await expect(trigger).toHaveCSS('opacity', '1')
  await context.close()

  expect(label.x + label.width).toBeLessThanOrEqual(button.x)
})

// The menu button's box stays 24 px in the card's corner while its hit area reaches 44 px, and
// the extra area never takes a tap meant for the title or priority.
test('e2e_a_cards_menu_button_has_a_44px_hit_area_on_touch', async ({ api: served, browser }) => {
  const context = await browser.newContext({
    hasTouch: true,
    isMobile: true,
    viewport: { width: 390, height: 844 },
  })
  const page = await context.newPage()
  await page.goto(`${served.url}/tickets`)
  const bug = card(page, 'CF-2')
  await bug.waitFor({ timeout: TIMEOUT })
  const trigger = bug.getByLabel('Actions for CF-2', { exact: true }).filter({ visible: true })
  await trigger.scrollIntoViewIfNeeded()
  const drawn = await box(trigger)
  const centre = { x: drawn.x + drawn.width / 2, y: drawn.y + drawn.height / 2 }
  // The card clips at 6 px beyond the glyph, so up and right reach the card's edge (about 17 px), not 20 px.
  const hits = await trigger.evaluate((button, c) => {
    const owner = (dx: number, dy: number) =>
      document.elementFromPoint(c.x + dx, c.y + dy)?.closest('button') === button
    return { left: owner(-20, 0), right: owner(15, 0), up: owner(0, -15), down: owner(0, 20) }
  }, centre)
  const [title, priority] = [
    await box(bug.getByRole('link', { name: 'A bug in flight' })),
    await box(bug.getByText('high', { exact: true })),
  ]
  const taken = await page.evaluate(
    (points) =>
      points.map(([x, y]) => document.elementFromPoint(x, y)?.closest('[data-js-menu]') !== null),
    [
      [title.x + 4, title.y + title.height / 2],
      [priority.x + priority.width / 2, priority.y + priority.height / 2],
    ] as [number, number][],
  )
  await context.close()

  expect(drawn.width).toBe(24)
  expect(hits).toStrictEqual({ left: true, right: true, up: true, down: true })
  expect(taken).toStrictEqual([false, false])
})

test('e2e_a_filter_with_no_match_says_so_on_the_board_and_the_list', async ({
  api: served,
  page,
}) => {
  await page.goto(`${served.url}/tickets`)
  await boardLoaded(page)
  await page.getByRole('searchbox', { name: 'Filter cards' }).fill('zzzqqq')
  await expect(page.getByText('No tickets match the filter.')).toBeVisible()

  await page.goto(`${served.url}/tickets/list`)
  await page.getByRole('searchbox', { name: 'Filter cards' }).fill('zzzqqq')
  const row = page.getByRole('row').filter({ hasText: 'No tickets match the filter.' })
  await expect(row).toBeVisible()
  await expect(row.getByRole('paragraph')).toBeVisible()
})

test('e2e_a_board_with_no_ticket_says_so', async ({ served, page }) => {
  for (const repository of [served.root, join(served.root, '..', 'second')])
    rmSync(join(repository, '.code-factory', 'tickets'), { recursive: true, force: true })
  await page.goto(`${served.url}/tickets`)
  await expect(page.getByText('No tickets yet.')).toBeVisible({ timeout: TIMEOUT })
})
