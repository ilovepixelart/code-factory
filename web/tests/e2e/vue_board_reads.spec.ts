// CF-1235: a page reads the board only while it shows it. A page that does not show the board
// reads it once, as the app opens; the Tickets page follows it with its poll. The page's clock is
// run by hand, so each poll tick fires when the test says.

import type { Page } from '@playwright/test'
import { TIMEOUT, expect, header, test } from './fixtures'

/** One tick of the board's poll. */
const TICK_MS = 3000

/** Count the page's reads of `/api/board` from now on. */
function boardReads(page: Page): () => number {
  let reads = 0
  page.on('request', (request) => {
    if (new URL(request.url()).pathname === '/api/board') reads += 1
  })
  return () => reads
}

async function opened(page: Page, url: string): Promise<void> {
  await page.clock.install()
  await page.goto(url)
  await expect(header(page).getByText('live', { exact: true })).toBeVisible({
    timeout: TIMEOUT,
  })
}

for (const path of ['/team', '/flow', '/inbox']) {
  test(`e2e_the_${path.slice(1)}_page_does_not_poll_the_board`, async ({ api, page }) => {
    await opened(page, `${api.url}${path}`)
    const reads = boardReads(page)

    await page.clock.runFor(5 * TICK_MS)

    expect(reads()).toBe(0)
  })
}

// The board, the sessions with their tickets, a ticket, a session with its ticket.
const SHOWING = {
  tickets: '/tickets',
  sessions: '/',
  ticket: '/tickets/sample/CF-1',
  session: '/sessions/s-block',
}

for (const [name, path] of Object.entries(SHOWING)) {
  test(`e2e_the_${name}_page_follows_the_board`, async ({ api, page }) => {
    await opened(page, `${api.url}${path}`)
    const reads = boardReads(page)

    await expect
      .poll(
        async () => {
          await page.clock.runFor(TICK_MS)
          return reads()
        },
        { timeout: TIMEOUT },
      )
      .toBeGreaterThanOrEqual(2)
  })
}

test('e2e_opening_the_tickets_page_reads_the_board', async ({ api, page }) => {
  await opened(page, `${api.url}/team`)
  const reads = boardReads(page)

  await page.getByRole('link', { name: 'Tickets' }).click()

  await expect.poll(reads, { timeout: TIMEOUT }).toBe(1)
})

test('e2e_leaving_the_tickets_page_stops_its_reads', async ({ api, page }) => {
  await opened(page, `${api.url}/tickets`)
  await page.getByRole('link', { name: 'Team' }).click()
  await expect(page).toHaveURL(/\/team$/)
  const reads = boardReads(page)

  await page.clock.runFor(5 * TICK_MS)

  expect(reads()).toBe(0)
})
