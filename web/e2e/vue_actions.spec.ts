// CF-218 acceptance flows: the card and column menus and the undo notice of the Vue board, served
// by the server over the writes sample state.

import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import type { Route } from '@playwright/test'
import { TIMEOUT, box, card, expect, menu, submenu, test, toasts, holdPoll } from './fixtures'

test('e2e_the_card_menu_changes_a_ticket', async ({ served, writesBoard }) => {
  let items = await menu(writesBoard, 'CF-3')
  await writesBoard.keyboard.press('Escape')
  await expect(items, 'closed by Escape').toBeHidden()
  await card(writesBoard, 'CF-3').click({ button: 'right' })
  // A right click opens the card's ContextMenu, named and filled as its button's menu, while that
  // button's DropdownMenu stays closed.
  await expect(items, 'opened by a right click').toBeVisible()
  await expect(items.getByRole('menuitem', { name: 'Duplicate' })).toBeVisible()
  await expect(
    card(writesBoard, 'CF-3').getByLabel('Actions for CF-3', { exact: true }),
    'the button menu stays closed',
  ).toHaveAttribute('aria-expanded', 'false')
  // An open menu takes the page's pointer events, so the click goes to where the heading is.
  const outside = await box(writesBoard.getByRole('heading', { name: 'Tickets', level: 1 }))
  await writesBoard.mouse.click(outside.x + outside.width / 2, outside.y + outside.height / 2)
  await expect(items, 'closed by a click outside').toBeHidden()
  items = await menu(writesBoard, 'CF-3')
  let priority = await submenu(items, 'Priority')
  await priority.getByRole('menuitemradio', { name: 'high', exact: true }).click()
  await expect.poll(() => served.ticket('CF-3')).toContain('priority: high')

  items = await menu(writesBoard, 'CF-3')
  priority = await submenu(items, 'Priority')
  // The board shows the new priority after its refresh: wait for it rather than read at once.
  await expect(priority.getByRole('menuitemradio', { name: 'high', exact: true })).toBeChecked()
  const moving = await submenu(items, 'Move to')
  await expect(moving.getByRole('menuitem', { name: 'Spec', exact: true })).toBeVisible()
  await expect(moving.getByRole('menuitem', { name: 'Build', exact: true })).toHaveCount(0)
  await holdPoll(writesBoard)
  await moving.getByRole('menuitem', { name: 'Spec', exact: true }).click()
  await expect.poll(() => served.ticket('CF-3')).toContain('stage: spec')
  await card(writesBoard.getByRole('region', { name: 'Spec', exact: true }), 'CF-3').waitFor({
    timeout: TIMEOUT,
  })

  const duplicate = (await menu(writesBoard, 'CF-3')).getByRole('menuitem', { name: 'Duplicate' })
  await holdPoll(writesBoard)
  await duplicate.click()
  await writesBoard.getByText('Declared (copy)').waitFor({ timeout: TIMEOUT })
  await expect(toasts(writesBoard)).toContainText('Duplicated CF-3 as CF-5')

  items = await menu(writesBoard, 'CF-3')
  await items.getByRole('menuitem', { name: 'Copy link' }).click()
  await items.getByText('Copied').waitFor({ timeout: TIMEOUT })
  const copied = await writesBoard.evaluate(() => navigator.clipboard.readText())

  expect(copied).toBe(`${served.url}/tickets/sample/CF-3`)
  expect(served.ticket('CF-5')).toContain('title: Declared (copy)')
})

// Far below the notice's own 8 seconds: it was cleared by the change, not by its timer.
const SOON_MS = 2000

test('e2e_a_success_clears_the_refusal_an_earlier_change_left', async ({ writesBoard }) => {
  const refusal = 'CF-2 needs a branch before Build'
  const notice = toasts(writesBoard)
  const moving = await submenu(await menu(writesBoard, 'CF-2'), 'Move to')
  await moving.getByRole('menuitem', { name: 'Build', exact: true }).click()
  await expect(notice).toContainText(refusal, { timeout: TIMEOUT })

  const priority = await submenu(await menu(writesBoard, 'CF-3'), 'Priority')
  const changed = writesBoard.waitForResponse(
    (r) => r.request().method() === 'PATCH' && r.url().endsWith('/api/tickets/sample/CF-3'),
  )
  await expect(notice, 'the refusal is still up when the change is sent').toContainText(refusal)
  await priority.getByRole('menuitemradio', { name: 'high', exact: true }).click()
  await changed
  const answered = Date.now()

  await expect(notice).not.toContainText(refusal, { timeout: TIMEOUT })
  expect(Date.now() - answered).toBeLessThan(SOON_MS)
})

test('e2e_an_archive_is_undone_from_the_notice', async ({ served, writesBoard }) => {
  await (await menu(writesBoard, 'CF-2')).getByRole('menuitem', { name: 'Archive' }).click()
  const notice = toasts(writesBoard)
  await notice.getByText('Archived CF-2').waitFor({ timeout: TIMEOUT })
  await expect.poll(() => served.ticket('CF-2')).toContain('archived: true')
  await notice.getByRole('button', { name: 'Undo' }).click()
  await expect.poll(() => served.ticket('CF-2')).not.toContain('archived')

  const activity = join(served.root, '.code-factory', 'tickets', 'CF-2', 'activity.jsonl')
  await expect(notice.getByText('Archived CF-2')).toBeHidden()
  expect(readFileSync(activity, 'utf8')).toContain('"kind": "restored"')
})

// The refusal needs CF-1's run to stay active: no follower to end it mid-test.
test.describe(() => {
  test.use({ follow: false })

  test('e2e_delete_asks_first_and_shows_a_refusal', async ({ served, writesBoard }) => {
    const dialog = writesBoard.getByRole('alertdialog', { name: 'Delete ticket' })
    await (await menu(writesBoard, 'CF-1')).getByRole('menuitem', { name: 'Delete' }).click()
    await dialog.getByRole('button', { name: 'Delete' }).click()
    await toasts(writesBoard)
      .getByText('an agent is running on this ticket; stop it first')
      .waitFor({ timeout: TIMEOUT })

    await (await menu(writesBoard, 'CF-2')).getByRole('menuitem', { name: 'Delete' }).click()
    await expect(dialog).toContainText('CF-2 Bare')
    await dialog.getByRole('button', { name: 'Cancel' }).click()
    const kept = served.ticket('CF-2')
    await (await menu(writesBoard, 'CF-2')).getByRole('menuitem', { name: 'Delete' }).click()
    await holdPoll(writesBoard)
    await dialog.getByRole('button', { name: 'Delete' }).click()
    await toasts(writesBoard).getByText('Deleted CF-2').waitFor({ timeout: TIMEOUT })
    await card(writesBoard, 'CF-2').waitFor({ state: 'detached', timeout: TIMEOUT })

    expect(kept).toContain('title: Bare')
    expect(served.ticket('CF-1')).toBeTruthy()
    expect(served.ticket('CF-2')).toBe('')
  })
})

test('e2e_the_column_menu_sets_a_limit', async ({ served, writesBoard }) => {
  const build = writesBoard.getByRole('region', { name: 'Build', exact: true })
  const columnMenu = build.getByLabel('Column menu for Build', { exact: true })
  const heading = build.getByRole('heading', { level: 2 })
  await columnMenu.click()
  const form = writesBoard.getByRole('form', { name: 'Limit for Build' })
  await form.getByRole('spinbutton').fill('3')
  await holdPoll(writesBoard)
  const held: Route[] = []
  await writesBoard.route('**/api/columns/build/limit', (route) => {
    held.push(route)
  })
  await form.getByRole('button', { name: 'Set limit' }).click()
  await expect.poll(() => held.length).toBeGreaterThan(0)
  await expect(form.getByRole('button', { name: 'Set limit' })).toBeDisabled()
  await held[0]?.continue()
  await writesBoard.unroute('**/api/columns/build/limit')
  await heading.getByText('1/3').waitFor({ timeout: TIMEOUT })
  const board = (): { wip: Record<string, number>; theme?: string } =>
    JSON.parse(readFileSync(join(served.home, 'board.json'), 'utf8')) as {
      wip: Record<string, number>
      theme?: string
    }
  const limited = board()

  await columnMenu.click()
  await form.getByRole('button', { name: 'Clear' }).click()
  await expect(heading).not.toContainText('/')
  const cleared = board()

  // The limit set on BRD before the four columns is written back as Spec's.
  expect(limited.wip).toStrictEqual({ spec: 2, build: 3 })
  expect(cleared.wip).toStrictEqual({ spec: 2 })
  expect(cleared.theme).toBe('dark')
})
