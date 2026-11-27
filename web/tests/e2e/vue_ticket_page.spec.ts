// The ticket page over the PostgreSQL board sample. Changes and split also use a tracked Git repo.

import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { delimiter, join } from 'node:path'
import {
  Served,
  TIMEOUT,
  card,
  codeFactory,
  dropSample,
  expect,
  git,
  prepareSample,
  start,
  test as boardTest,
} from './fixtures'

const TITLE = 'A bug in flight'
const TICKET = '/tickets/sample/CF-2'
const API = '/api' + TICKET

const test = boardTest.extend<{ tracked: Served }>({
  tracked: async ({}, use) => {
    const directory = mkdtempSync(join(tmpdir(), 'factory-ticket-page-'))
    const schema = prepareSample('board')
    const repo = join(directory, 'sample')
    const env = {
      ...process.env,
      CODE_FACTORY_DB_SCHEMA: schema,
      CODE_FACTORY_STATE_DIR: join(directory, 'state'),
      PATH: [directory, process.env.PATH].join(delimiter),
    }
    let stop: (() => void) | undefined
    try {
      mkdirSync(repo)
      git(repo, 'init', '--initial-branch=main')
      git(repo, 'commit', '--allow-empty', '-m', 'Initial repository')
      git(repo, 'switch', '-c', 'ticket/cf-2')
      writeFileSync(join(repo, 'change.txt'), 'The ticket changes this file.\n')
      git(repo, 'add', 'change.txt')
      git(repo, 'commit', '-m', 'Commit the ticket change')
      git(repo, 'switch', 'main')

      // Keep the split live until the UI observes its real run; no model account is used.
      writeFileSync(join(directory, 'claude'), '#!/bin/sh\nexec sleep 120\n', { mode: 0o700 })
      codeFactory(['track', repo], env)
      const server = await start(schema, { env })
      stop = server.stop
      await use(new Served(server.url, schema))
    } finally {
      stop?.()
      dropSample(schema)
      rmSync(directory, { recursive: true, force: true })
    }
  },
})

test('e2e_the_ticket_page_shows_a_ticket', async ({ served, writesBoard }) => {
  const edited = await served.api('PATCH', API, {
    description: 'Some **bold** words.',
    blocked_by: 'CF-1',
    budget: '3',
  })
  expect(edited.status).toBe(200)
  const comment = await served.api('POST', `${API}/comments`, { text: 'Looks right' })
  expect(comment.status).toBe(200)
  await writesBoard.reload()
  await card(writesBoard, 'CF-2').getByRole('link', { name: TITLE }).click()
  await writesBoard.getByRole('link', { name: 'Open as page' }).click()
  const crumbs = writesBoard.getByRole('navigation', { name: 'Breadcrumb' })
  const ticket = writesBoard.getByRole('form', { name: 'Edit ticket CF-2' })

  await expect(writesBoard).toHaveURL(served.url + TICKET)
  await expect(crumbs.getByRole('link', { name: 'Tickets' })).toHaveAttribute('href', '/tickets')
  await expect(crumbs.getByRole('heading')).toHaveText('CF-2')
  await expect(ticket.getByRole('textbox', { name: 'Title' })).toHaveValue(TITLE)
  await ticket.getByRole('button', { name: 'Budget', exact: true }).click()
  await expect(ticket.getByRole('textbox', { name: 'Budget' })).toHaveValue('3')
  await ticket.getByRole('button', { name: 'Blocked by', exact: true }).click()
  await expect(ticket.getByRole('textbox', { name: 'Blocked by' })).toHaveValue('CF-1')
  await ticket.getByRole('tab', { name: 'Preview', exact: true }).click()
  await expect(ticket.getByRole('strong').filter({ hasText: 'bold' })).toBeVisible()
  const blocker = ticket
    .getByRole('list', { name: 'Blocked by' })
    .getByRole('link')
    .filter({ hasText: 'CF-1' })
  await expect(blocker).toContainText('Specs written')
  await expect(blocker).toHaveAttribute('href', '/tickets/sample/CF-1')
  await ticket.getByRole('button', { name: 'Add a document' }).click()
  await expect(ticket.getByText('.code-factory/tickets/CF-2/requirements.md')).toBeVisible()
  for (const words of [
    'Blocked by',
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

test('e2e_the_ticket_activity_shows_the_newest_comment_first', async ({ served, writesBoard }) => {
  for (const text of [
    'Earlier comment for the activity test',
    'Latest comment for the activity test',
  ]) {
    const result = await served.api('POST', `${API}/comments`, { text })
    expect(result.status).toBe(200)
  }
  await writesBoard.goto(served.url + TICKET)

  const comments = writesBoard
    .getByRole('list', { name: 'Activity' })
    .getByRole('listitem')
    .filter({ hasText: 'comment for the activity test' })
  await expect(comments).toHaveText([
    /Latest comment for the activity test/,
    /Earlier comment for the activity test/,
  ])
})

// A title cleared and left is refused on the field and restored; the ticket stays readable.
test('e2e_a_cleared_title_is_refused_and_the_ticket_keeps_it', async ({ served, writesBoard }) => {
  await writesBoard.goto(served.url + TICKET)
  const ticket = writesBoard.getByRole('form', { name: 'Edit ticket CF-2' })
  const title = ticket.getByRole('textbox', { name: 'Title' })
  await expect(title).toHaveValue(TITLE, { timeout: TIMEOUT })

  await title.fill('   ')
  await title.press('Enter')

  await expect(ticket.getByRole('alert')).toHaveText('A ticket needs a title.')
  await expect(title).toHaveValue(TITLE)
  await expect(ticket.getByText('Not saved')).toBeVisible()
  expect((await served.fields('CF-2')).title).toBe(TITLE)
  await writesBoard.reload()
  await expect(
    writesBoard.getByRole('form', { name: 'Edit ticket CF-2' }).getByRole('textbox', {
      name: 'Title',
    }),
  ).toHaveValue(TITLE, { timeout: TIMEOUT })
})

// CF-471: the board's first answer lands while the ticket is still being read; the ticket's
// answer must still fill the form.
test('e2e_a_slow_ticket_answer_still_shows_its_title', async ({ browser, served }) => {
  const context = await browser.newContext()
  const page = await context.newPage()
  const boardAnswered = page.waitForResponse((r) => r.url().endsWith('/api/board'), {
    timeout: TIMEOUT,
  })
  await page.route(`**${API}`, async (route) => {
    await boardAnswered
    await route.continue()
  })
  await page.goto(served.url + TICKET)

  await expect(
    page.getByRole('form', { name: 'Edit ticket CF-2' }).getByRole('textbox', { name: 'Title' }),
  ).toHaveValue(TITLE, { timeout: TIMEOUT })
  await context.close()
})

// CF-836-R1: a ticket page longer than the window scrolls inside the window; the document
// itself never grows past it, so no empty band shows below the page once scrolled down. The
// branch brings the Changes section, whose heading holds screen-reader text near the page's end.
test('e2e_a_long_ticket_page_scrolls_inside_the_window', async ({ tracked, page }) => {
  await page.setViewportSize({ width: 1600, height: 500 })
  await page.goto(tracked.url + TICKET)
  const changes = page.getByRole('region', { name: /^Changes/ })
  const changedFile = changes.getByRole('table', { name: 'change.txt' })
  await expect(changedFile).toBeVisible({ timeout: TIMEOUT })
  await changedFile.scrollIntoViewIfNeeded()

  const heights = await page.evaluate(() => ({
    document: document.scrollingElement?.scrollHeight ?? 0,
    window: window.innerHeight,
    content: document.querySelector('[data-scroller]')?.scrollHeight ?? 0,
    scrolled: document.querySelector('[data-scroller]')?.scrollTop ?? 0,
  }))

  expect(heights.content).toBeGreaterThan(heights.window)
  expect(heights.document).toBe(heights.window)
  expect(heights.scrolled).toBeGreaterThan(0)
})

// CF-996-R4 (CF-996-A1): a split starts from the page, and its run shows among the ticket's runs.
test('e2e_a_split_is_started_from_the_ticket_page', async ({ tracked, page }) => {
  // The owner starts this one explicitly. Its hold keeps the automatic follower off it.
  const created = await tracked.api('POST', '/api/tickets', {
    repository: 'sample',
    title: 'Plan a rollout',
    blocked: 'Waiting for the owner to start a split',
  })
  expect(created.status, JSON.stringify(created.json)).toBe(201)
  const { id } = created.json as { id: string }
  const path = `/tickets/sample/${id}`
  await page.goto(tracked.url + path)
  await page.getByRole('button', { name: 'Split', exact: true }).click({ timeout: TIMEOUT })
  await page.getByLabel('What to split this ticket into').fill('Two tickets, please.')

  const started = page.waitForResponse((response) => response.url().endsWith(`/api${path}/split`))
  await page.getByRole('button', { name: 'Start split' }).click()

  const response = await started
  expect(response.status(), await response.text()).toBe(201)
  await expect(
    page.getByText(`Started a split of ${id}; its tickets appear under it as the run files them`),
  ).toBeVisible({ timeout: TIMEOUT })
  await expect(page.getByLabel('What to split this ticket into')).toHaveCount(0)
  await expect(page.getByRole('region', { name: 'Status' })).toContainText('Agent · Split')
  const running = page.getByRole('region', { name: /^Agent/ })
  await expect(running.getByText(/Iteration 1 on Split/)).toBeVisible()
  await running.getByRole('button', { name: 'Stop agent' }).click()
  await expect(running.getByRole('button', { name: 'Stop agent' })).toHaveCount(0)
})

// CF-996-R5 (CF-996-A2): a refusal shows under the field, and the brief stays typed.
test('e2e_a_refused_split_shows_its_reason', async ({ served, writesBoard }) => {
  expect((await served.api('POST', '/api/agents/stop')).status).toBe(200)
  await writesBoard.goto(served.url + TICKET)
  await writesBoard.getByRole('button', { name: 'Split', exact: true }).click({ timeout: TIMEOUT })
  const field = writesBoard.getByLabel('What to split this ticket into')
  await field.fill('Two tickets, please.')

  const refused = writesBoard.waitForResponse((response) => response.url().endsWith(API + '/split'))
  await writesBoard.getByRole('button', { name: 'Start split' }).click()

  expect((await refused).status()).toBe(409)
  await expect(
    writesBoard.getByRole('alert').filter({ hasText: 'agents are stopped' }),
  ).toBeVisible()
  await expect(field).toHaveValue('Two tickets, please.')
})
