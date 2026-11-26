// CF-225 acceptance flows: editing a ticket in the Vue panel and on its page, served by the
// server over the writes sample state.

import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import type { Locator, Page, Route } from '@playwright/test'
import { TIMEOUT, card, expect, git, test, toasts, addLabels } from './fixtures'
import { OWNER_COOKIE } from './owner'

function panel(page: Page, id: string): Locator {
  return page.getByRole('form', { name: `Edit ticket ${id}` })
}

test('e2e_the_panel_saves_each_field', async ({ served, writesBoard }) => {
  await card(writesBoard, 'CF-2').click({ position: { x: 200, y: 60 } })
  const form = panel(writesBoard, 'CF-2')
  await form.waitFor({ timeout: TIMEOUT })
  const header = await writesBoard
    .getByRole('dialog')
    .getByRole('heading', { level: 2 })
    .innerText()
  const title = form.getByRole('textbox', { name: 'Title' })
  await title.fill('Renamed in the panel')
  await title.press('Tab')
  await expect.poll(() => served.ticket('CF-2')).toContain('title: Renamed in the panel')
  await form.getByLabel('Priority').selectOption('high')
  await expect.poll(() => served.ticket('CF-2')).toContain('priority: high')
  await addLabels(form, 'x', 'y')
  await expect.poll(() => served.ticket('CF-2')).toContain('labels: x, y')
  await expect(form.getByText('Saved', { exact: true })).toBeVisible()
  await form.getByRole('link', { name: 'Open as page' }).click()
  await writesBoard.getByRole('navigation', { name: 'Breadcrumb' }).waitFor({ timeout: TIMEOUT })

  expect(header.split(/\s+/).filter(Boolean)).toStrictEqual(['sample', '/', 'CF-2'])
  expect(writesBoard.url().endsWith('/tickets/sample/CF-2')).toBe(true)
})

test('e2e_a_refused_field_is_not_saved', async ({ served, writesBoard }) => {
  await card(writesBoard, 'CF-2').getByRole('link', { name: 'Bare' }).click()
  const form = panel(writesBoard, 'CF-2')
  await form.getByLabel('Stage').selectOption('review')
  await toasts(writesBoard)
    .getByText('CF-2 moves one column at a time: Build is next')
    .waitFor({ timeout: TIMEOUT })

  await expect(form.getByText('Not saved', { exact: true })).toBeVisible()
  expect(served.ticket('CF-2')).not.toContain('stage:')
  expect(writesBoard.url().endsWith('/tickets')).toBe(true)
})

// CF-1201-R3: a refused Caused by shows the board's reason under it and keeps its text.
test('e2e_a_refused_caused_by_shows_its_reason_under_it', async ({ served, writesBoard }) => {
  await writesBoard.goto(`${served.url}/tickets/sample/CF-2`)
  const form = panel(writesBoard, 'CF-2')
  await form.getByLabel('Type').selectOption('bug')
  const caused = form.getByLabel('Caused by')
  await caused.fill('CF-9999')
  await caused.press('Tab')

  await expect(form.getByRole('alert').getByText('no ticket CF-9999')).toBeVisible()
  await expect(caused).toHaveValue('CF-9999')
  await expect(form.getByText('Not saved', { exact: true })).toBeVisible()
  expect(served.ticket('CF-2')).not.toContain('caused_by')
})

// CF-1359-R3: a Branch no branch has is refused under the field, which keeps its text.
test('e2e_a_branch_no_branch_has_is_refused_under_the_field', async ({ served, writesBoard }) => {
  await writesBoard.goto(`${served.url}/tickets/sample/CF-2`)
  const form = panel(writesBoard, 'CF-2')
  const branch = form.getByLabel('Branch')
  await branch.fill('feat/not-made-yet')
  await branch.press('Tab')

  await expect(
    form.getByRole('alert').getByText('no branch feat/not-made-yet exists'),
  ).toBeVisible()
  await expect(branch).toHaveValue('feat/not-made-yet')
  await expect(form.getByText('Not saved', { exact: true })).toBeVisible()
  expect(served.ticket('CF-2')).not.toContain('branch:')
})

test('e2e_comments_and_answers_are_added', async ({ served, writesBoard }) => {
  await writesBoard.goto(`${served.url}/tickets/sample/CF-1`)
  const page = panel(writesBoard, 'CF-1')
  await page.waitFor({ timeout: TIMEOUT })
  const comment = page.getByRole('textbox', { name: 'New comment' })
  await comment.fill('Ship it')
  await page.getByRole('button', { name: 'Send comment' }).click()
  await page.getByText('You commented').waitFor({ timeout: TIMEOUT })
  await page.getByRole('textbox', { name: 'Answer to Which size?' }).fill('large')
  await page.getByRole('button', { name: 'Answer', exact: true }).click()
  await page.getByText('Answered Which size?').waitFor({ timeout: TIMEOUT })
  const spec = readFileSync(
    join(served.root, '.code-factory', 'tickets', 'CF-1', 'spec.md'),
    'utf8',
  )

  await expect(comment).toHaveValue('')
  expect(spec).toContain('- Which size?\n  Answer: large\n')
  await expect(page.getByRole('button', { name: 'Update' })).toHaveCount(2, { timeout: TIMEOUT })
})

test('e2e_the_footer_archives_and_deletes', async ({ served, writesBoard }) => {
  await card(writesBoard, 'CF-2').getByRole('link', { name: 'Bare' }).click()
  const form = panel(writesBoard, 'CF-2')
  await form.getByRole('button', { name: 'Archive' }).click()
  await toasts(writesBoard).getByText('Archived CF-2').waitFor({ timeout: TIMEOUT })
  await form.waitFor({ state: 'hidden', timeout: TIMEOUT })
  const archived = served.ticket('CF-2')

  await writesBoard.goto(`${served.url}/tickets/sample/CF-3`)
  const page = panel(writesBoard, 'CF-3')
  await page.getByRole('button', { name: 'Delete' }).click()
  await writesBoard
    .getByRole('dialog', { name: 'Delete ticket' })
    .getByRole('button', { name: 'Delete' })
    .click()
  await writesBoard.waitForURL(`${served.url}/tickets`, { timeout: TIMEOUT })

  expect(archived).toContain('archived: true')
  expect(served.ticket('CF-3')).toBe('')
})

test('e2e_a_delete_says_it_can_be_undone_and_the_undo_brings_the_ticket_back', async ({
  served,
  writesBoard,
}) => {
  const before = served.ticket('CF-3')
  await writesBoard.goto(`${served.url}/tickets/sample/CF-3`)
  await panel(writesBoard, 'CF-3').getByRole('button', { name: 'Delete' }).click()
  const dialog = writesBoard.getByRole('dialog', { name: 'Delete ticket' })

  await expect(dialog).toContainText('Undo in the notice that follows brings it back')
  await expect(dialog).not.toContainText('cannot be undone')
  await dialog.getByRole('button', { name: 'Delete' }).click()
  await writesBoard.waitForURL(`${served.url}/tickets`, { timeout: TIMEOUT })
  expect(served.ticket('CF-3')).toBe('')
  await toasts(writesBoard).getByRole('button', { name: 'Undo' }).click()

  await expect.poll(() => served.ticket('CF-3'), { timeout: TIMEOUT }).toBe(before)
})

test('e2e_typing_survives_another_field_saving', async ({ served, writesBoard }) => {
  const held: Route[] = []
  await card(writesBoard, 'CF-2').getByRole('link', { name: 'Bare' }).click()
  const form = panel(writesBoard, 'CF-2')
  await form.waitFor({ timeout: TIMEOUT })
  await writesBoard.route('**/api/tickets/sample/CF-2', async (route) => {
    if (route.request().method() === 'PATCH') held.push(route)
    else await route.continue()
  })
  await form.getByLabel('Priority').selectOption('high')
  await expect.poll(() => held.length).toBeGreaterThan(0)
  await form.getByLabel('Labels').fill('typed meanwhile')
  // The save ends by reading the ticket again: the field must survive that read.
  const reread = writesBoard.waitForResponse(
    (r) => r.url().endsWith('/api/tickets/sample/CF-2') && r.request().method() === 'GET',
    { timeout: TIMEOUT },
  )
  await held[0]?.continue()
  await writesBoard.unroute('**/api/tickets/sample/CF-2')
  await form.getByText('Saved', { exact: true }).waitFor({ timeout: TIMEOUT })
  await (await reread).finished()

  await expect(form.getByLabel('Labels')).toHaveValue('typed meanwhile')
  expect(served.ticket('CF-2')).toContain('priority: high')
})

// CF-255: a save from the form carries the field changed there, not stale copies of the rest.
test('e2e_a_save_keeps_changes_made_elsewhere', async ({ served, writesBoard }) => {
  await card(writesBoard, 'CF-2').getByRole('link', { name: 'Bare' }).click()
  const form = panel(writesBoard, 'CF-2')
  await form.waitFor({ timeout: TIMEOUT })
  git(served.root, 'branch', 'feat/CF-2')
  const answer = await fetch(`${served.url}/api/tickets/sample/CF-2`, {
    method: 'PATCH',
    headers: { Cookie: OWNER_COOKIE, 'Content-Type': 'application/json' },
    body: JSON.stringify({ branch: 'feat/CF-2' }),
  })
  expect(answer.status).toBe(200)
  const title = form.getByRole('textbox', { name: 'Title' })
  await title.fill('Renamed in the panel')
  await title.press('Tab')
  await expect.poll(() => served.ticket('CF-2')).toContain('title: Renamed in the panel')
  const again = await fetch(`${served.url}/api/tickets/sample/CF-2`, {
    method: 'PATCH',
    headers: { Cookie: OWNER_COOKIE, 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: 'Renamed elsewhere' }),
  })
  expect(again.status).toBe(200)
  await addLabels(form, 'x')
  await expect.poll(() => served.ticket('CF-2')).toContain('labels: x')

  expect(served.ticket('CF-2')).toContain('branch: feat/CF-2')
  expect(served.ticket('CF-2')).toContain('title: Renamed elsewhere')
})
