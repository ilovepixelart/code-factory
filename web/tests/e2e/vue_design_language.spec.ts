// CF-266 acceptance flows: every screen follows the board's design language, over the writes
// sample state (the api sample for sessions).

import type { Locator, Page } from '@playwright/test'
import {
  OPEN_OVERLAY,
  TIMEOUT,
  box,
  card,
  contrast,
  expect,
  hold,
  scroller,
  settle,
  test,
  variant,
  useTheme,
} from './fixtures'

test('e2e_archive_rows_show_restore_as_a_secondary_button', async ({ served, writesBoard }) => {
  await writesBoard.goto(`${served.url}/archive`)
  const row = writesBoard.getByRole('row').filter({ hasText: 'CF-4' })
  await row.waitFor({ timeout: TIMEOUT })
  const restore = row.getByRole('button', { name: 'Restore' })
  const opacity = (): Promise<string> => restore.evaluate((e) => getComputedStyle(e).opacity)
  const headers = writesBoard
    .getByRole('row')
    .filter({ has: writesBoard.getByRole('columnheader') })

  expect(await opacity()).toBe('1')
  await expect(restore).toHaveAttribute('data-variant', 'outline')
  await expect(row.getByRole('button', { name: 'Delete CF-4' })).toBeVisible()
  await expect(headers).not.toContainText('Repository')
})

test('e2e_an_archive_row_on_a_phone_is_a_card_with_no_sideways_scroll', async ({
  served,
  writesBoard,
}) => {
  await writesBoard.setViewportSize({ width: 390, height: 800 })
  await writesBoard.goto(`${served.url}/archive`)
  await writesBoard.getByRole('row').filter({ hasText: 'CF-4' }).waitFor({ timeout: TIMEOUT })

  const overflow = await writesBoard.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  await expect(writesBoard.getByRole('columnheader')).toHaveCount(0)

  expect(overflow).toBe(0)
  await expect(writesBoard.getByRole('button', { name: 'Restore CF-4' })).toBeVisible()
})

test('e2e_a_session_row_does_not_repeat_its_repository', async ({ api: served, page }) => {
  await page.goto(`${served.url}/`)
  const group = 'sample'
  const rows = page.getByRole('list', { name: `Sessions in ${group}`, exact: true })

  await expect(rows.getByRole('listitem')).not.toHaveCount(0)
  await expect(rows).not.toContainText(group)
})

test('e2e_a_session_page_says_it_is_loading', async ({ api: served, page }) => {
  const { promise: held, resolve: release }: PromiseWithResolvers<void> = Promise.withResolvers()
  let asked = false
  await page.route(/\/api\/sessions\/[^/]+\/timeline/, async (route) => {
    asked = true
    await held
    await route.continue()
  })
  await page.goto(`${served.url}/sessions/s-idle`)
  // The page has asked for the timeline, and waits for it.
  await expect.poll(() => asked).toBe(true)
  const body = page.getByRole('document')
  await expect(body).toContainText('Loading')
  await expect(body).not.toContainText('unknown repository')
  release()
})

test('e2e_memory_starts_where_reading_pages_start', async ({ served, writesBoard }) => {
  await writesBoard.goto(`${served.url}/inbox`)
  const inbox = writesBoard.getByRole('heading', { name: /^Questions/, level: 2 })
  await inbox.waitFor({ timeout: TIMEOUT })
  const inboxTop = (await box(inbox)).y
  await writesBoard.goto(`${served.url}/memory`)
  const first = writesBoard.getByRole('meter', { name: 'Loaded into every agent session' })
  await first.waitFor({ timeout: TIMEOUT })
  // What needs the owner comes first on the page (CF-1171), so its first block is the one to align.
  const memoryTop = await writesBoard.getByRole('main').evaluate((main) => {
    const body = main.querySelector('.page-wide, .page-reading')
    const top = body?.firstElementChild?.getBoundingClientRect().top
    if (top === undefined) throw new Error('the memory page has no first block')
    return top
  })

  await expect(writesBoard.getByRole('region', { name: /^Search results/ })).toHaveCount(0)
  expect(Math.abs(memoryTop - inboxTop)).toBeLessThanOrEqual(1)
})

/** Elements of the page's scroller, the board's columns strip aside, that scroll sideways. */
function sideways(page: Page): Promise<string[]> {
  return scroller(page).evaluate((main) =>
    [main, ...main.querySelectorAll('*')]
      .filter((e) => !e.closest('[data-board-columns]'))
      .filter((e) => {
        const x = getComputedStyle(e).overflowX
        return (e === main || x === 'auto' || x === 'scroll') && e.scrollWidth > e.clientWidth + 1
      })
      .map((e) => `${e.tagName}.${[...e.classList].slice(0, 3).join('.')}`),
  )
}

/** For each screen, an element it draws once its data has loaded. */
const DRAWN: Record<string, (page: Page) => Locator> = {
  '/tickets': (page) => card(page, 'CF-2'),
  '/tickets/list': (page) => page.getByRole('cell', { name: 'CF-2', exact: true }),
  '/archive': (page) => page.getByRole('row').filter({ hasText: 'CF-4' }),
  '/memory': (page) => page.getByRole('meter', { name: 'Loaded into every agent session' }),
  '/inbox': (page) => page.getByRole('heading', { name: /^Questions/, level: 2 }),
  '/': (page) => page.getByRole('heading', { name: /^Sessions/, level: 2 }),
}

test('e2e_every_screen_fits_1024', async ({ served, browser }) => {
  const context = await browser.newContext({ viewport: { width: 1024, height: 800 } })
  const page = await context.newPage()
  // CF-1020-R2: the sheet's slide held at its start until the test finishes it.
  await hold(page)
  for (const [path, drawn] of Object.entries(DRAWN)) {
    await page.goto(`${served.url}${path}`)
    await drawn(page).waitFor({ timeout: TIMEOUT })
    expect(await sideways(page), path).toStrictEqual([])
  }
  await page.goto(`${served.url}/tickets`)
  await card(page, 'CF-2').waitFor({ timeout: TIMEOUT })
  const filter = await box(page.getByPlaceholder('Filter cards'))
  const create = await box(page.getByRole('button', { name: /New ticket/ }))
  expect(
    Math.abs(create.y + create.height / 2 - (filter.y + filter.height / 2)),
  ).toBeLessThanOrEqual(4)
  await card(page, 'CF-2').getByRole('link', { name: 'Bare', exact: true }).click()
  const sheet = page.getByRole('form', { name: 'Edit ticket CF-2' })
  await sheet.waitFor({ timeout: TIMEOUT })
  await settle(page, OPEN_OVERLAY)
  // The sheet's form sits inside its one pixel left border.
  const edge = await box(sheet)
  expect([edge.x, edge.x + edge.width]).toStrictEqual([1, 1024])
  await page.keyboard.press('Escape')
  // The closed sheet pops its history entry; a load sent before that lands is undone by it.
  await expect
    .poll(() =>
      page.evaluate(
        () => (history.state as Record<string, unknown> | null)?.codeFactoryOverlay ?? null,
      ),
    )
    .toBeNull()
  await page.goto(`${served.url}/tickets/list`)
  const id = page.getByRole('cell', { name: 'CF-2', exact: true })
  await id.waitFor({ timeout: TIMEOUT })
  const rows = await id.evaluate((e) => {
    const text = document.createRange()
    text.selectNodeContents(e)
    return new Set([...text.getClientRects()].map((r) => Math.round(r.top))).size
  })
  expect(rows).toBe(1)
  await page.goto(`${served.url}/archive`)
  const remove = page
    .getByRole('row')
    .filter({ hasText: 'CF-4' })
    .getByRole('button', { name: /Delete/ })
  await remove.waitFor({ state: 'attached', timeout: TIMEOUT })
  const drawn = await box(remove)
  expect(drawn.x + drawn.width).toBeLessThanOrEqual(1024)
  await context.close()
})

test('e2e_opening_a_panel_focuses_its_header', async ({ writesBoard }) => {
  await card(writesBoard, 'CF-2').getByRole('link', { name: 'Bare', exact: true }).click()
  const header = writesBoard.getByRole('dialog').getByRole('heading', { name: /CF-2/, level: 2 })
  await header.waitFor({ timeout: TIMEOUT })

  await expect
    .poll(() => header.evaluate((e) => e === document.activeElement), { timeout: TIMEOUT })
    .toBe(true)
})

// The board's quiet text, as the board sample draws it: a column's count, a card's high priority.
const CONTRAST_PROBES: [string, (page: Page) => Locator][] = [
  [
    'a column count',
    (page) =>
      page
        .getByRole('region', { name: 'Review', exact: true })
        .getByRole('heading', { level: 2 })
        .getByText('0', { exact: true }),
  ],
  ['a high priority', (page) => card(page, 'CF-2').getByText('high', { exact: true })],
]

test('e2e_text_meets_the_contrast_minimum', async ({ api: served, page }) => {
  await page.goto(`${served.url}/tickets`)
  await card(page, 'CF-2').waitFor({ timeout: TIMEOUT })
  // CF-1020-R3: the theme's colours held where they start easing until `useTheme` finishes them.
  await hold(page)
  for (const theme of ['light', 'dark']) {
    await useTheme(page, theme)
    for (const [probe, locate] of CONTRAST_PROBES) {
      const text = locate(page)
      await expect(text).toBeVisible()
      expect(await contrast(text), `${theme} ${probe}`).toBeGreaterThanOrEqual(4.5)
    }
  }
})

// Every button's words read 4.5:1 on its fill in both themes, and a chosen button (the current
// page of a list, an active toggle) stands off what it sits on: a fill no lighter than the card
// it sits on sinks into the card or the page.
test('e2e_every_design_page_button_reads_and_a_chosen_one_stands_out', async ({
  api: served,
  page,
}) => {
  await page.goto(`${served.url}/design`)
  await page
    .getByRole('group', { name: 'Disabled buttons' })
    .getByRole('button', { name: 'secondary', exact: true })
    .waitFor({ timeout: TIMEOUT })
  await hold(page)
  const main = page.getByRole('main')
  const chosen = [main.getByRole('link', { name: '2', exact: true })]
  for (const theme of ['light', 'dark']) {
    await useTheme(page, theme)
    for (const button of await main.getByRole('button').filter({ visible: true }).all()) {
      const name = `${String(await button.textContent())} ${String(await button.getAttribute('aria-label'))}`
      expect(await contrast(button), `${theme} ${name}`).toBeGreaterThanOrEqual(4.5)
    }
    for (const button of chosen) {
      await expect(button).toHaveAttribute('aria-current', 'page')
      const name = String(await button.textContent())
      expect(await contrast(button, true), `${theme} chosen ${name}`).toBeGreaterThanOrEqual(1.2)
    }
  }
})

// CF-1204: a card no longer lists the sessions on main, so the working chip is read where it lives.
test('e2e_a_working_session_chip_meets_the_contrast_minimum', async ({ api: served, page }) => {
  await page.goto(`${served.url}/`)
  const chip = page
    .getByRole('listitem')
    .filter({ has: page.getByText('zz', { exact: true }) })
    .getByText('Working', { exact: true })
  await chip.waitFor({ timeout: TIMEOUT })
  await hold(page)
  for (const theme of ['light', 'dark']) {
    await useTheme(page, theme)
    // Success is the secondary Badge (docs/design.md, Theme).
    await expect(chip).toHaveAttribute('data-slot', 'badge')
    expect(await variant(chip)).toBe('secondary')
    expect(await contrast(chip), theme).toBeGreaterThanOrEqual(4.5)
  }
})

test('e2e_an_unknown_route_says_not_found', async ({ served, writesBoard }) => {
  await writesBoard.goto(`${served.url}/no-such-page`)
  await writesBoard.getByRole('heading', { name: 'Not found' }).waitFor({ timeout: TIMEOUT })
  const main = writesBoard.getByRole('main')

  await expect(main.getByRole('link', { name: 'Tickets' })).toHaveCount(1)
  await expect(main).not.toContainText('served by the board')
})

/** The left and right edges of a page body, inside its padding or, with `outer`, outside it. */
function edges(page: Page, outer = false): Promise<[number, number]> {
  return page.getByRole('main').evaluate((main, whole) => {
    const e = main.querySelector('.page-wide, .page-reading')
    if (!e) throw new Error('main has no page body')
    const box = e.getBoundingClientRect()
    const style = getComputedStyle(e)
    const [left = 0, right = 0] = whole
      ? [0, 0]
      : [style.paddingLeft, style.paddingRight].map(parseFloat)
    return [Math.round(box.left + left), Math.round(box.right - right)] as [number, number]
  }, outer)
}

test('e2e_every_screen_uses_the_board_width', async ({ served, writesBoard }) => {
  const board = await edges(writesBoard)
  for (const path of ['/tickets/list', '/', '/inbox', '/archive', '/memory']) {
    await writesBoard.goto(`${served.url}${path}`)
    await DRAWN[path]?.(writesBoard).waitFor({ timeout: TIMEOUT })
    await expect
      .poll(() => edges(writesBoard), { message: path, timeout: TIMEOUT })
      .toStrictEqual(board)
  }
  // The ticket page's form brings its own padding: its body spans the board's whole box.
  await writesBoard.goto(`${served.url}/tickets`)
  const whole = await edges(writesBoard, true)
  await writesBoard.goto(`${served.url}/tickets/sample/CF-1`)
  // Measured once its content has rendered and the page scrolls, where a scrollbar takes width.
  await expect(writesBoard.getByRole('form', { name: 'Edit ticket CF-1' })).toBeVisible()
  await expect
    .poll(() => scroller(writesBoard).evaluate((m) => m.scrollHeight > m.clientHeight))
    .toBe(true)
  await expect
    .poll(() => edges(writesBoard, true), { message: 'ticket page', timeout: TIMEOUT })
    .toStrictEqual(whole)
})

/** The space between the page scroller's edges and its page body's content: left, right, top,
 *  bottom. */
function margins(page: Page): Promise<number[]> {
  return scroller(page).evaluate((main) => {
    const body = main.querySelector('.page-wide')
    if (!body) throw new Error('the page scroller has no page body')
    main.scrollTop = 0
    const outer = main.getBoundingClientRect()
    const box = body.getBoundingClientRect()
    const style = getComputedStyle(body)
    const [left, right, top, bottom] = [
      style.paddingLeft,
      style.paddingRight,
      style.paddingTop,
      style.paddingBottom,
    ].map(parseFloat)
    return [
      box.left + (left ?? 0) - outer.left,
      outer.right - (box.right - (right ?? 0)),
      box.top + (top ?? 0) - outer.top,
      bottom ?? 0,
    ].map(Math.round)
  })
}

test('e2e_a_page_s_margins_are_equal_on_all_four_sides', async ({ served, writesBoard }) => {
  for (const path of ['/tickets', '/tickets/list', '/', '/inbox', '/archive', '/memory']) {
    await writesBoard.goto(`${served.url}${path}`)
    await DRAWN[path]?.(writesBoard).waitFor({ timeout: TIMEOUT })
    await expect
      .poll(async () => new Set(await margins(writesBoard)).size, {
        message: path,
        timeout: TIMEOUT,
      })
      .toBe(1)
  }
})
