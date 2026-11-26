// The core flow of the board in a real browser, signed in as the owner, over the `board` sample:
// the board read from Postgres, a ticket page, create, edit, move, archive and the Memory page.

import type { Page } from '@playwright/test'
import { TIMEOUT, addLabels, card, cards, expect, menu, submenu, test, toasts } from './fixtures'

function column(page: Page, label: string) {
  return page.getByRole('region', { name: label, exact: true })
}

test('e2e_the_board_shows_the_tickets_the_database_holds', async ({ served, writesBoard }) => {
  const bug = card(column(writesBoard, 'Build'), 'CF-2')
  await bug.waitFor({ timeout: TIMEOUT })
  const text = await bug.innerText()

  for (const value of [
    'CF-2',
    '↑ CF-1',
    'Bug',
    'High',
    'A bug in flight',
    'ui',
    'agents',
    'sample',
  ]) {
    expect(text, value).toContain(value)
  }
  await expect(card(column(writesBoard, 'Spec'), 'CF-1')).toContainText('Specs written')
  await expect(card(column(writesBoard, 'Merged'), 'CF-5')).toContainText('Merged already')
  await expect(card(writesBoard, 'CF-4'), 'an archived ticket is off the board').toHaveCount(0)
  await expect(cards(writesBoard)).toHaveCount(6)
  expect((await served.api('GET', '/api/repositories')).json).toStrictEqual(['sample', 'second'])
})

test('e2e_the_ticket_page_shows_its_documents_and_fields', async ({ served, writesBoard }) => {
  await writesBoard.goto(`${served.url}/tickets/sample/CF-1`)
  const form = writesBoard.getByRole('form', { name: 'Edit ticket CF-1' })
  await form.getByRole('textbox', { name: 'Title' }).waitFor({ timeout: TIMEOUT })

  await expect(form.getByRole('textbox', { name: 'Title' })).toHaveValue('Specs written')
  await expect(form.getByRole('button', { name: 'Labels', exact: true })).toHaveText('docs')
  // The first written document (Requirements) shows, rendered from its markdown.
  await expect(writesBoard.getByText('The first requirement')).toBeVisible()
  await writesBoard.goto(`${served.url}/tickets/sample/CF-99`)
  await expect(writesBoard.getByText('No ticket CF-99')).toBeVisible()
})

test('e2e_a_ticket_is_created_from_the_dialog', async ({ served, writesBoard }) => {
  await writesBoard.keyboard.press('n')
  const form = writesBoard.getByRole('dialog', { name: 'New ticket' })
  await form.waitFor({ timeout: TIMEOUT })
  await form.getByRole('textbox', { name: 'Title', exact: true }).fill('Crash on save')
  await form.getByLabel('Type').selectOption('bug')
  await addLabels(form, 'ui', 'data')
  await form.getByRole('button', { name: 'Create ticket' }).click()
  await form.waitFor({ state: 'hidden', timeout: TIMEOUT })
  await card(writesBoard, 'CF-8').waitFor({ timeout: TIMEOUT })

  await expect(toasts(writesBoard)).toContainText('Created CF-8')
  const ticket = await served.fields('CF-8')
  expect([ticket.title, ticket.type, ticket.labels]).toStrictEqual([
    'Crash on save',
    'bug',
    'ui, data',
  ])
})

test('e2e_the_card_menu_edits_moves_and_archives', async ({ served, writesBoard }) => {
  const priority = await submenu(await menu(writesBoard, 'CF-3'), 'Priority')
  await priority.getByRole('menuitemradio', { name: 'High', exact: true }).click()
  await expect.poll(async () => (await served.fields('CF-3')).priority).toBe('high')

  const back = await submenu(await menu(writesBoard, 'CF-2'), 'Move to')
  await back.getByRole('menuitem', { name: 'Spec', exact: true }).click()
  await expect(card(column(writesBoard, 'Spec'), 'CF-2')).toBeVisible({ timeout: TIMEOUT })

  const moves = await submenu(await menu(writesBoard, 'CF-2'), 'Move to')
  await moves.getByRole('menuitem', { name: 'Build', exact: true }).click()
  await expect(card(column(writesBoard, 'Build'), 'CF-2')).toBeVisible({ timeout: TIMEOUT })
  expect((await served.fields('CF-2')).branch).toBe('ticket/cf-2')

  await (
    await menu(writesBoard, 'CF-6', 'second')
  )
    .getByRole('menuitem', { name: 'Archive' })
    .click()
  await toasts(writesBoard).getByText('Archived CF-6').waitFor({ timeout: TIMEOUT })
  await expect(card(writesBoard, 'CF-6', 'second')).toHaveCount(0)
  await writesBoard.goto(`${served.url}/archive`)
  await expect(writesBoard.getByText('Elsewhere')).toBeVisible({ timeout: TIMEOUT })
})

test('e2e_the_memory_page_lists_reviews_and_retires_entries', async ({ served, writesBoard }) => {
  await writesBoard.goto(`${served.url}/memory`)
  await writesBoard.getByText('Keep it small and test first').waitFor({ timeout: TIMEOUT })
  await expect(writesBoard.getByText('The gate ran twice on one tree')).toBeVisible()
  await expect(writesBoard.getByText('Ship small pull requests')).toBeVisible()

  await writesBoard
    .getByRole('searchbox', { name: 'Search what the repository knows' })
    .fill('gate twice')
  await expect(writesBoard.getByRole('region', { name: 'Search results' })).toBeVisible({
    timeout: TIMEOUT,
  })
})

test('e2e_an_entry_added_on_the_memory_page_is_stored', async ({ served, writesBoard }) => {
  await writesBoard.goto(`${served.url}/memory`)
  await writesBoard.getByRole('button', { name: 'Add an entry' }).click()
  const form = writesBoard.getByRole('form', { name: /entry/i })
  await form.getByRole('textbox', { name: 'Statement' }).fill('Read the log before guessing')
  await form.getByRole('textbox', { name: 'Why' }).fill('It names the cause')
  await form.getByRole('textbox', { name: 'Source' }).fill('CF-2')
  await form.getByRole('button', { name: /save|add/i }).click()
  await writesBoard.getByText('Read the log before guessing').waitFor({ timeout: TIMEOUT })

  const page = (await served.api('GET', '/api/memory')).json as {
    unreviewed: { statement: string; why: string }[]
  }
  expect(page.unreviewed.map((e) => e.statement)).toContain('Read the log before guessing')
})

test('e2e_no_page_of_the_board_says_not_found', async ({ served, writesBoard }) => {
  for (const path of ['/tickets', '/tickets/sample/CF-1', '/memory', '/archive', '/team']) {
    // The shell reads the inbox count as the page opens: wait for that answer, then look.
    const counted = writesBoard.waitForResponse((r) => r.url().endsWith('/api/inbox/count'))
    await writesBoard.goto(`${served.url}${path}`)
    await counted
    await writesBoard.getByRole('navigation', { name: 'Pages' }).waitFor({ timeout: TIMEOUT })
    await expect(writesBoard.getByText(/not found/i), path).toHaveCount(0)
  }
  await writesBoard.goto(`${served.url}/inbox`)
  await expect(writesBoard.getByText('Nothing needs you')).toBeVisible()
})

test('e2e_an_answer_to_a_question_nobody_asked_is_refused_and_the_count_stays_zero', async ({
  served,
}) => {
  const answer = await served.api('POST', '/api/tickets/sample/CF-1/answers', {
    document: 'spec',
    index: 0,
    question: 'nothing asked',
    answer: 'x',
  })
  expect(answer.status).toBeGreaterThanOrEqual(400)
  expect((await served.api('GET', '/api/inbox/count')).json).toStrictEqual({
    count: 0,
    latest: '',
  })
})

test('e2e_an_installed_harness_starts_the_matching_agent_setup', async ({
  served,
  writesBoard,
}) => {
  await writesBoard.route('**/api/harnesses', (route) =>
    route.fulfill({ json: { claude: false, codex: true, srt: true } }),
  )
  await writesBoard.goto(`${served.url}/agents`)
  const local = writesBoard.getByRole('region', { name: 'Local harnesses' })
  await expect(local.getByText('Unavailable')).toBeVisible()
  await expect(local.getByText('Installed', { exact: true })).toBeVisible()
  await local.getByRole('button', { name: 'Set up Codex agent' }).click()
  await expect(
    writesBoard.getByRole('form', { name: 'New agent' }).getByLabel('Harness'),
  ).toHaveValue('codex')
})
