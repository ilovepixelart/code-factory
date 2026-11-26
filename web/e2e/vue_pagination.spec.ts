// CF-1191 acceptance flows: the Archive asks the board for one page, the Tickets list pages the
// board it holds, and both draw the shared page control, served by the server over the writes
// sample without the run follower, so the tickets the tests write stay as written.

import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import type { Page } from '@playwright/test'
import { Served, TIMEOUT, expect, serve, test as base, useTheme } from './fixtures'

const HOUR = 3600

const test = base.extend<{ served: Served }>({
  served: async ({}, use) => {
    const { served, stop } = await serve('writes', 'false', false)
    await use(served)
    stop()
  },
})

const stamp = (at: number): string => new Date(at * 1000).toISOString().replace(/\.\d{3}Z$/, 'Z')

function ticket(served: Served, id: string, front: string): void {
  const folder = join(served.root, '.code-factory', 'tickets', id)
  mkdirSync(folder, { recursive: true })
  writeFileSync(join(folder, 'ticket.md'), `---\nid: ${id}\n${front}---\n`)
}

/** CF-100 to CF-124 archived an hour apart, CF-124 last; the sample's own archived CF-4 put back. */
function archived(served: Served): void {
  ticket(served, 'CF-4', 'title: Archived\n')
  const now = Date.now() / 1000
  for (let n = 100; n < 125; n++) {
    const id = `CF-${String(n)}`
    ticket(served, id, `title: Archived ${String(n)}\narchived: true\n`)
    writeFileSync(
      join(served.root, '.code-factory', 'tickets', id, 'activity.jsonl'),
      `${JSON.stringify({ at: stamp(now - (130 - n) * HOUR), kind: 'archived' })}\n`,
    )
  }
}

/** `CF-<from>` to `CF-<to>`, counting down when `from` is the larger. */
const ids = (from: number, to: number): string[] =>
  Array.from(
    { length: Math.abs(to - from) + 1 },
    (_, i) => `CF-${String(from > to ? from - i : from + i)}`,
  )

const control = (page: Page, list: string) =>
  page.getByRole('navigation', { name: `Pages of ${list}` })
const range = (page: Page, list: string) => control(page, list).getByTestId('page-range')

/** The ids the page's table lists: the first cell of each body row. */
async function rowIds(page: Page): Promise<string[]> {
  return page
    .getByRole('table')
    .getByRole('row')
    .evaluateAll((rows) =>
      rows.flatMap((row) => {
        const cell = row.querySelector('td')
        return cell ? [cell.textContent.trim()] : []
      }),
    )
}

// CF-1191-R1, CF-1191-R3, CF-1191-R9
test('the_page_lives_in_the_address', async ({ served, page }) => {
  archived(served)
  const asked: string[] = []
  page.on('request', (request) => {
    if (request.url().includes('/api/archive')) asked.push(new URL(request.url()).search)
  })
  await page.goto(`${served.url}/archive?size=10`)
  const nav = control(page, 'archived tickets')
  await expect(range(page, 'archived tickets')).toHaveText('1 to 10 of 25', { timeout: TIMEOUT })

  await nav.getByRole('link', { name: '2', exact: true }).click()

  await expect(range(page, 'archived tickets')).toHaveText('11 to 20 of 25')
  expect(await rowIds(page)).toStrictEqual(ids(114, 105))
  await expect(nav.getByRole('link', { name: '2', exact: true })).toHaveAttribute(
    'aria-current',
    'page',
  )
  await expect(nav.getByTestId('page-number')).toHaveText(['1', '2', '3'])
  expect(new URL(page.url()).search).toBe('?page=2&size=10')
  await expect(page.getByRole('heading', { name: /^Archived tickets\s*,\s*25$/ })).toBeVisible()
  expect(asked.at(-1)).toBe('?q=&sort=&dir=&page=2&size=10')

  await page.goBack()

  await expect(range(page, 'archived tickets')).toHaveText('1 to 10 of 25')
  expect(new URL(page.url()).search).toBe('?size=10')
  expect((await rowIds(page))[0]).toBe('CF-124')
})

// CF-1191-R4
test('search_filter_sort_or_size_return_to_page_one', async ({ served, page }) => {
  archived(served)
  const second = `${served.url}/archive?page=2&size=10`
  const shown = range(page, 'archived tickets')

  await page.goto(second)
  await expect(shown).toHaveText('11 to 20 of 25', { timeout: TIMEOUT })
  await page.getByRole('searchbox', { name: 'Search archived tickets' }).fill('CF-11')
  await expect.poll(() => rowIds(page)).toStrictEqual(ids(119, 110))
  await expect(control(page, 'archived tickets')).toHaveCount(0)
  expect(new URL(page.url()).searchParams.get('page')).toBeNull()

  await page.goto(second)
  await expect(shown).toHaveText('11 to 20 of 25', { timeout: TIMEOUT })
  await page.getByRole('link', { name: 'Id', exact: true }).click()
  await expect(shown).toHaveText('1 to 10 of 25')
  expect((await rowIds(page))[0]).toBe('CF-124')
  expect(new URL(page.url()).searchParams.get('page')).toBeNull()
  expect(new URL(page.url()).searchParams.get('size')).toBe('10')

  await page.goto(second)
  await expect(shown).toHaveText('11 to 20 of 25', { timeout: TIMEOUT })
  await control(page, 'archived tickets').getByRole('button', { name: '10 per page' }).click()
  await page.getByRole('link', { name: '25 per page' }).click()
  await expect.poll(async () => (await rowIds(page)).length).toBe(25)
  await expect(control(page, 'archived tickets')).toHaveCount(0)
  expect(new URL(page.url()).search).toBe('?size=25')
})

// CF-1191-R5
test('a_page_past_the_end_shows_the_last', async ({ served, page }) => {
  archived(served)

  await page.goto(`${served.url}/archive?page=9&size=10`)

  const nav = control(page, 'archived tickets')
  await expect(range(page, 'archived tickets')).toHaveText('21 to 25 of 25', { timeout: TIMEOUT })
  expect(await rowIds(page)).toStrictEqual(ids(104, 100))
  await expect(nav.getByRole('link', { name: 'Next ›' })).toHaveCount(0)
  await expect.poll(() => new URL(page.url()).search).toBe('?page=3&size=10')

  await page.goto(`${served.url}/archive?page=abc&size=7`)

  await expect.poll(async () => (await rowIds(page)).length, { timeout: TIMEOUT }).toBe(25)
  await expect(nav).toHaveCount(0)
})

// CF-1191-R2
test('one_page_or_none_draws_no_control', async ({ served, page }) => {
  archived(served)
  const search = page.getByRole('searchbox', { name: 'Search archived tickets' })
  const nav = control(page, 'archived tickets')

  await page.goto(`${served.url}/archive`)
  await expect.poll(async () => (await rowIds(page)).length, { timeout: TIMEOUT }).toBe(25)
  await expect(nav).toHaveCount(0)
  await search.fill('CF-10')
  await expect.poll(async () => (await rowIds(page)).length).toBe(10)
  await expect(nav).toHaveCount(0)
  await search.fill('zebra')
  await expect(page.getByText('No archived ticket matches “zebra”')).toBeVisible()
  await expect(nav).toHaveCount(0)
})

// CF-1191-R10
test('browser_paged_lists_use_the_shared_control', async ({ served, page }) => {
  for (let n = 100; n < 220; n++) ticket(served, `CF-${String(n)}`, `title: Listed ${String(n)}\n`)

  await page.goto(`${served.url}/tickets/list?q=Listed&sort=id&dir=asc`)
  const nav = control(page, 'tickets')
  await expect(range(page, 'tickets')).toHaveText('1 to 50 of 120', { timeout: TIMEOUT })
  await nav.getByRole('link', { name: '3', exact: true }).click()

  await expect(range(page, 'tickets')).toHaveText('101 to 120 of 120')
  expect(await rowIds(page)).toStrictEqual(ids(200, 219))
  expect(new URL(page.url()).searchParams.get('page')).toBe('3')

  await page.getByRole('searchbox', { name: 'Filter cards' }).fill('CF-21')

  await expect.poll(() => rowIds(page)).toStrictEqual(ids(210, 219))
  await expect(nav).toHaveCount(0)
  expect(new URL(page.url()).searchParams.get('page')).toBeNull()
})

// CF-1191-R13
test('page_nav_design_rules', async ({ served, page }) => {
  archived(served)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(`${served.url}/archive?page=2&size=10`)
  const nav = control(page, 'archived tickets')
  await expect(range(page, 'archived tickets')).toHaveText('11 to 20 of 25', { timeout: TIMEOUT })

  await expect(nav.getByTestId('page-of')).toHaveText('Page 2 of 3')
  await expect(nav.getByTestId('page-of')).toBeVisible()
  await expect(nav.getByRole('link', { name: '‹ Previous' })).toBeVisible()
  await expect(nav.getByRole('link', { name: 'Next ›' })).toBeVisible()
  await expect(nav.getByRole('button', { name: '10 per page' })).toHaveText('10 per page')
  await expect(nav.getByRole('button', { name: '10 per page' })).toBeVisible()
  for (const number of await nav.getByTestId('page-number').all()) {
    await expect(number).toBeHidden()
  }
  for (const theme of ['light', 'dark']) {
    await useTheme(page, theme)
    const sideways = await page.evaluate(() => {
      const main = document.querySelector('[data-scroller]')
      return [
        document.documentElement.scrollWidth - document.documentElement.clientWidth,
        main ? main.scrollWidth - main.clientWidth : 0,
      ]
    })
    expect(sideways, theme).toStrictEqual([0, 0])
  }
  const inline = await page.evaluate(() => ({
    handlers: [...document.querySelectorAll('*')].filter((e) =>
      [...e.attributes].some((a) => a.name.startsWith('on')),
    ).length,
    scripts: [...document.querySelectorAll('script:not([src])')].length,
    styles: [...document.querySelectorAll('body style')].length,
  }))
  expect(inline).toStrictEqual({ handlers: 0, scripts: 0, styles: 0 })
})

// CF-1191-R14
test('the_design_page_shows_the_page_control', async ({ served, page }) => {
  await page.goto(`${served.url}/design`)

  const nav = control(page, 'the example list')
  await expect(range(page, 'the example list')).toHaveText('11 to 20 of 247', { timeout: TIMEOUT })
  await expect(nav.getByRole('link', { name: '2', exact: true })).toHaveAttribute(
    'aria-current',
    'page',
  )
})
