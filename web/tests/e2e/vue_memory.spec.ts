// CF-213 acceptance flows: the Memory, Archive and Design pages of the Vue board, served by the
// server over the writes sample state.

import type { Locator, Page } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { TIMEOUT, expect, scroller, test } from './fixtures'

const RULE =
  '---\nkind: rule\ndate: 2026-10-01\nsource: conversation\nreviewed: 2026-10-02\n---\nKeep every rule small\n'
const LESSON =
  '---\nkind: lesson\ndate: 2026-10-02\nsource: CF-2\nreviewed: 2026-10-02\n---\nThe gate ran twice\n'

test('e2e_the_memory_page_shows_and_searches', async ({ served, writesBoard }) => {
  served.writeMemory({
    '2026-10-01-keep-every-rule-small.md': RULE,
    '2026-10-02-the-gate-ran-twice.md': LESSON,
  })
  await writesBoard.goto(`${served.url}/memory`)
  const core = writesBoard.getByRole('region', { name: /^Core\b/ })
  await core.getByText('Keep every rule small').waitFor({ timeout: TIMEOUT })
  const lesson = core.getByRole('listitem', { name: 'The gate ran twice' })
  const unguarded = lesson.getByText('no guard', { exact: true })
  await expect(unguarded).toBeHidden()
  await lesson.getByText('The gate ran twice').click()
  await writesBoard
    .getByRole('searchbox', { name: 'Search what the repository knows' })
    .fill('rule')
  const results = writesBoard.getByRole('region', { name: 'Search results' })
  await results
    .getByText('sample/.code-factory/memory/2026-10-01-keep-every-rule-small.md')
    .waitFor({ timeout: TIMEOUT })

  await expect(unguarded).toBeVisible()
  await expect(core.getByRole('listitem')).toHaveCount(2)
  expect(writesBoard.url().endsWith('/memory?q=rule')).toBe(true)
})

// CF-367: a heading's count is read apart from its title, after a comma.
test('e2e_a_section_heading_reads_its_title_and_count_apart', async ({ served, writesBoard }) => {
  served.writeMemory({
    '2026-10-01-keep-every-rule-small.md': RULE,
    '2026-10-02-the-gate-ran-twice.md': LESSON,
  })
  await writesBoard.goto(`${served.url}/memory`)
  const core = writesBoard.getByRole('heading', { name: /^Core/, level: 2 })
  await core.waitFor({ timeout: TIMEOUT })
  const history = writesBoard.getByRole('heading', { name: /^History/, level: 2 })

  await expect(core).toHaveAccessibleName(/^Core\s*,\s*2$/)
  await expect(history).toHaveCount(0)
  await expect(writesBoard.getByRole('region', { name: /^Core\s*,\s*2$/ })).toHaveCount(1)
})

/** Search the Memory page for `words`; the results region once a row holding `path` shows. */
async function search(page: Page, url: string, words: string, path: string): Promise<Locator> {
  await page.goto(`${url}/memory`)
  await page.getByRole('searchbox', { name: 'Search what the repository knows' }).fill(words)
  const results = page.getByRole('region', { name: 'Search results' })
  await results.getByText(path).waitFor({ timeout: TIMEOUT })
  return results
}

test('e2e_a_ticket_result_opens_its_ticket', async ({ served, writesBoard }) => {
  served.editTicket('CF-2', 'rank: 2\n---\n', 'rank: 2\n---\nThe quokka sleeps here.\n')
  const path = 'sample/.code-factory/tickets/CF-2/ticket.md'
  const results = await search(writesBoard, served.url, 'quokka', path)

  await results.getByRole('link', { name: path }).click()

  await writesBoard.waitForURL('**/tickets/sample/CF-2', { timeout: TIMEOUT })
  await expect(writesBoard.getByRole('heading', { name: 'CF-2' })).toBeVisible()
})

// CF-1171-R4 (CF-1171-A2): the result opens the entry's closed row, in view.
test('e2e_a_memory_result_opens_its_entry', async ({ served, writesBoard }) => {
  served.writeMemory({ '2026-10-02-the-gate-ran-twice.md': LESSON })
  const path = 'sample/.code-factory/memory/2026-10-02-the-gate-ran-twice.md'
  const results = await search(writesBoard, served.url, 'ran twice', path)
  const row = results.getByRole('listitem').filter({ hasText: path })
  const snippet = await row.textContent()

  await row.getByRole('link', { name: path }).click()

  await writesBoard.waitForURL('**#2026-10-02-the-gate-ran-twice', { timeout: TIMEOUT })
  expect(snippet).not.toContain('---')
  const entry = writesBoard
    .getByRole('region', { name: /^Core\b/ })
    .getByRole('listitem', { name: 'The gate ran twice' })
  await expect(entry).toHaveAttribute('id', '2026-10-02-the-gate-ran-twice')
  await expect(entry).toBeInViewport()
  await expect(entry.getByRole('button', { name: 'Mark reviewed' })).toBeVisible()
})

// CF-1195: the search results are paged by the server and the heading counts every match.
test('e2e_search_results_page_and_count_every_match', async ({ served, writesBoard }) => {
  const entries = Object.fromEntries(
    Array.from({ length: 12 }, (_, n) => [
      `2026-10-01-zephyr-${String(n + 10)}.md`,
      `---\nkind: rule\ndate: 2026-10-01\nsource: conversation\n---\nZephyr rule ${String(n + 10)}\n`,
    ]),
  )
  served.writeMemory(entries)
  await writesBoard.goto(`${served.url}/memory?q=zephyr&size=10`)
  const results = writesBoard.getByRole('region', { name: /^Search results/ })
  const nav = writesBoard.getByRole('navigation', { name: 'Pages of the search results' })

  await expect(results.getByRole('listitem')).toHaveCount(10, { timeout: TIMEOUT })
  await expect(results.getByRole('heading', { name: /^Search results/ })).toHaveAccessibleName(
    /^Search results\s*,\s*12$/,
  )
  await expect(nav.getByTestId('page-range')).toHaveText('1 to 10 of 12')
  await nav.getByRole('link', { name: 'Next ›' }).click()
  await expect(nav.getByTestId('page-range')).toHaveText('11 to 12 of 12')
  await expect(results.getByRole('listitem')).toHaveCount(2)
  expect(writesBoard.url()).toContain('page=2')
})

test('e2e_the_archive_restores_and_deletes', async ({ served, writesBoard }) => {
  const ticket = join(served.root, '.code-factory', 'tickets', 'CF-2', 'ticket.md')
  served.editTicket('CF-2', 'rank: 2\n', 'rank: 2\narchived: true\n')
  await writesBoard.goto(`${served.url}/archive`)
  const table = writesBoard.getByRole('table')
  await table.getByRole('link', { name: 'Id' }).click()
  await writesBoard.waitForURL('**/archive?sort=id&dir=desc', { timeout: TIMEOUT })
  await table.getByRole('link', { name: 'Id' }).click()
  await writesBoard.waitForURL('**/archive?sort=id&dir=asc', { timeout: TIMEOUT })
  const rows = table.getByRole('row').filter({ has: writesBoard.getByRole('cell') })
  const ids = rows.getByRole('cell').filter({ hasText: /^CF-\d+$/ })
  await expect.poll(async () => (await ids.allTextContents())[0]).toBe('CF-2')
  const order = await ids.allTextContents()
  await table.getByRole('button', { name: 'Restore CF-2' }).click()
  await rows.filter({ hasText: 'CF-2' }).waitFor({ state: 'detached', timeout: TIMEOUT })
  await table.getByRole('button', { name: 'Delete CF-4' }).click()
  await writesBoard.getByRole('alertdialog').getByRole('button', { name: 'Delete' }).click()
  await rows.filter({ hasText: 'CF-4' }).waitFor({ state: 'detached', timeout: TIMEOUT })

  expect(order).toStrictEqual(['CF-2', 'CF-4'])
  expect(readFileSync(ticket, 'utf8')).not.toContain('archived')
  expect(served.ticket('CF-4')).toBe('')
})

test('e2e_the_design_page_shows_the_language', async ({ served, writesBoard }) => {
  await writesBoard.goto(`${served.url}/design`)
  for (const heading of ['Theme', 'Button', 'Fields', 'Badges and states', 'Components']) {
    await writesBoard
      .getByRole('heading', { name: heading, exact: true })
      .waitFor({ timeout: TIMEOUT })
  }

  await expect(writesBoard.getByTestId('swatch-stage-spec')).toBeVisible()
})

const LONG =
  '---\nkind: rule\ndate: 2026-10-03\nsource: chat\nwhy: Long lines must wrap\n---\n' +
  `Keep ${'src/very/deeply/nested/module/path/'.repeat(4)}file.rs readable on a phone\n`

/** A lesson whose guard, a test name with no space in it, is wider than a phone. */
const GUARDED =
  '---\nkind: lesson\ndate: 2026-10-04\nsource: CF-9\nwhy: It broke twice\n' +
  `guard: ${'a_test_function_named_at_length_'.repeat(3)}end\n---\nKeep the guard named\n`

// CF-1171-R8 (CF-1171-A3): at a phone's width the page scrolls only vertically.
test('e2e_the_memory_page_fits_a_phone', async ({ served, writesBoard }) => {
  served.writeMemory({
    '2026-10-01-keep-every-rule-small.md': RULE,
    '2026-10-02-the-gate-ran-twice.md': LESSON,
    '2026-10-03-keep-it-readable.md': LONG,
    '2026-10-04-keep-the-guard-named.md': GUARDED,
  })
  await writesBoard.setViewportSize({ width: 390, height: 844 })
  await writesBoard.goto(`${served.url}/memory`)
  await writesBoard
    .getByRole('region', { name: /^Core\b/ })
    .getByRole('listitem', { name: 'Keep every rule small' })
    .waitFor({ timeout: TIMEOUT })
  const wide = (e: Element) => e.scrollWidth - e.clientWidth

  const root = await writesBoard.evaluate(() => {
    const html = document.documentElement
    return html.scrollWidth - html.clientWidth
  })
  expect([await scroller(writesBoard).evaluate(wide), root]).toStrictEqual([0, 0])
})
