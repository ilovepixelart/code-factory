// CF-217 acceptance flows: the ticket page of the Vue app, served by the server over the
// writes sample state.

import { Served, TIMEOUT, card, expect, test } from './fixtures'
import { OWNER_COOKIE } from './owner'

async function send(served: Served, method: string, path: string, body: object): Promise<void> {
  const answer = await fetch(`${served.url}${path}`, {
    method,
    headers: { Cookie: OWNER_COOKIE, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  expect([200, 201]).toContain(answer.status)
}

test('e2e_the_ticket_page_shows_a_ticket', async ({ served, writesBoard }) => {
  await send(served, 'PATCH', '/api/tickets/sample/CF-2', {
    description: 'Some **bold** words.',
    blocked_by: 'CF-1',
    budget: '3',
  })
  await send(served, 'POST', '/api/tickets/sample/CF-2/comments', { text: 'Looks right' })
  await writesBoard.reload()
  await card(writesBoard, 'CF-2').getByRole('link', { name: 'Bare' }).click()
  await writesBoard.getByRole('link', { name: 'Open as page' }).click()
  await writesBoard.getByRole('navigation', { name: 'Breadcrumb' }).waitFor({ timeout: TIMEOUT })
  const ticket = writesBoard.getByRole('form', { name: 'Edit ticket CF-2' })
  await ticket.getByRole('textbox', { name: 'Title' }).waitFor({ timeout: TIMEOUT })

  expect(writesBoard.url().endsWith('/tickets/sample/CF-2')).toBe(true)
  const crumbs = await writesBoard.getByRole('navigation', { name: 'Breadcrumb' }).innerText()
  expect(crumbs.split(/\s+/).filter(Boolean)).toStrictEqual(['Tickets', '/', 'CF-2'])
  await expect(ticket.getByRole('textbox', { name: 'Title' })).toHaveValue('Bare')
  await expect(ticket.getByLabel('Budget')).toHaveValue('3')
  await expect(ticket.getByRole('textbox', { name: 'Blocked by' })).toHaveValue('CF-1')
  await expect(ticket.getByRole('strong').filter({ hasText: 'bold' })).toHaveCount(1)
  const blocker = ticket
    .getByRole('list', { name: 'Blocked by' })
    .getByRole('link')
    .filter({ hasText: 'CF-1' })
  await expect(blocker).toContainText('Specs written')
  await expect(blocker).toHaveAttribute('href', '/tickets/sample/CF-1')
  for (const words of [
    'Blocked by',
    '.code-factory/tickets/CF-2/requirements.md',
    'You commented',
    'Looks right',
    'Edited the description',
    'Set blocked by to CF-1',
  ]) {
    await expect(ticket, words).toContainText(words)
  }
})

test('e2e_a_missing_ticket_says_so', async ({ served, writesBoard }) => {
  await writesBoard.goto(`${served.url}/tickets/sample/CF-99`)
  await expect(writesBoard.getByText('No ticket CF-99')).toBeVisible()
})

// A title cleared and left is refused on the field and restored; the ticket stays readable.
test('e2e_a_cleared_title_is_refused_and_the_ticket_keeps_it', async ({ served, writesBoard }) => {
  await writesBoard.goto(`${served.url}/tickets/sample/CF-2`)
  const ticket = writesBoard.getByRole('form', { name: 'Edit ticket CF-2' })
  const title = ticket.getByRole('textbox', { name: 'Title' })
  await expect(title).toHaveValue('Bare', { timeout: TIMEOUT })

  await title.fill('   ')
  await title.press('Enter')

  await expect(ticket.getByRole('alert')).toHaveText('A ticket needs a title.')
  await expect(title).toHaveValue('Bare')
  await expect(ticket.getByText('Not saved')).toBeVisible()
  const answer = await fetch(`${served.url}/api/tickets/sample/CF-2`, {
    headers: { Cookie: OWNER_COOKIE },
  })
  expect(answer.status).toBe(200)
  await writesBoard.reload()
  await expect(
    writesBoard.getByRole('form', { name: 'Edit ticket CF-2' }).getByRole('textbox', {
      name: 'Title',
    }),
  ).toHaveValue('Bare', { timeout: TIMEOUT })
})

// CF-471: the board's first answer lands while the ticket is still being read; the ticket's
// answer must still fill the form.
test('e2e_a_slow_ticket_answer_still_shows_its_title', async ({ browser, served }) => {
  const context = await browser.newContext()
  const page = await context.newPage()
  const boardAnswered = page.waitForResponse((r) => r.url().endsWith('/api/board'), {
    timeout: TIMEOUT,
  })
  await page.route('**/api/tickets/sample/CF-2', async (route) => {
    await boardAnswered
    await route.continue()
  })
  await page.goto(`${served.url}/tickets/sample/CF-2`)

  await expect(
    page.getByRole('form', { name: 'Edit ticket CF-2' }).getByRole('textbox', { name: 'Title' }),
  ).toHaveValue('Bare', { timeout: TIMEOUT })
  await context.close()
})

// CF-836-R1: a ticket page longer than the window scrolls inside the window; the document
// itself never grows past it, so no empty band shows below the page once scrolled down. The
// branch brings the Changes section, whose heading holds screen-reader text near the page's end.
test('e2e_a_long_ticket_page_scrolls_inside_the_window', async ({ served, writesBoard }) => {
  served.editTicket('CF-2', 'rank: 2\n', 'rank: 2\nbranch: feat/CF-2\n')
  await writesBoard.setViewportSize({ width: 1600, height: 500 })
  await writesBoard.goto(`${served.url}/tickets/sample/CF-2`)
  await writesBoard.getByRole('region', { name: /^Changes/ }).waitFor({ timeout: TIMEOUT })

  const heights = await writesBoard.evaluate(() => ({
    document: document.scrollingElement?.scrollHeight ?? 0,
    window: window.innerHeight,
    content: document.querySelector('[data-scroller]')?.scrollHeight ?? 0,
  }))

  expect(heights.content).toBeGreaterThan(heights.window)
  expect(heights.document).toBe(heights.window)
})

// CF-996-R4 (CF-996-A1): a split starts from the page, and its run shows among the ticket's runs.
test('e2e_a_split_is_started_from_the_ticket_page', async ({ served, writesBoard }) => {
  await writesBoard.goto(`${served.url}/tickets/sample/CF-2`)
  await writesBoard.getByRole('button', { name: 'Split', exact: true }).click({ timeout: TIMEOUT })
  await writesBoard.getByLabel('What to split this ticket into').fill('Two tickets, please.')

  await writesBoard.getByRole('button', { name: 'Start split' }).click()

  await expect(
    writesBoard.getByText('Started a split of CF-2; its proposal reaches the Inbox when it ends'),
  ).toBeVisible({ timeout: TIMEOUT })
  await expect(writesBoard.getByLabel('What to split this ticket into')).toHaveCount(0)
})

// CF-996-R5 (CF-996-A2): a refusal shows under the field, and the brief stays typed.
test('e2e_a_refused_split_shows_its_reason', async ({ served, writesBoard }) => {
  await writesBoard.route('**/api/tickets/sample/CF-2/split', (route) =>
    route.fulfill({ status: 409, json: { error: 'an agent is already running on this ticket' } }),
  )
  await writesBoard.goto(`${served.url}/tickets/sample/CF-2`)
  await writesBoard.getByRole('button', { name: 'Split', exact: true }).click({ timeout: TIMEOUT })
  const field = writesBoard.getByLabel('What to split this ticket into')
  await field.fill('Two tickets, please.')

  await writesBoard.getByRole('button', { name: 'Start split' }).click()

  await expect(writesBoard.getByText('an agent is already running on this ticket')).toBeVisible({
    timeout: TIMEOUT,
  })
  await expect(field).toHaveValue('Two tickets, please.')
})
