// CF-223 acceptance flows: selecting cards and the bulk bar of the Vue board, served by the
// server over the writes sample state.

import type { Locator, Page } from '@playwright/test'
import { TIMEOUT, card, expect, menu, test, toasts } from './fixtures'

async function select(...cards: Locator[]): Promise<void> {
  for (const item of cards)
    await item
      .getByRole('paragraph')
      .filter({ has: item.page().getByRole('link') })
      .click({ modifiers: ['ControlOrMeta'] })
}

function bar(page: Page): Locator {
  return page.getByRole('toolbar', { name: 'Bulk actions' })
}

test('e2e_cards_are_selected_and_cleared', async ({ served, writesBoard }) => {
  const first = card(writesBoard, 'CF-2')
  const second = card(writesBoard, 'CF-1', 'second')
  const third = card(writesBoard, 'CF-3')
  await third.getByText('sample', { exact: true }).click() // a plain click on a card's footer chooses nothing
  const panel = writesBoard.getByRole('form', { name: 'Edit ticket CF-3' })
  await expect(panel).toBeVisible() // it opened the card's panel
  await expect(bar(writesBoard)).toHaveCount(0)
  await writesBoard.keyboard.press('Escape')
  await panel.waitFor({ state: 'hidden' })
  await third.hover()
  const actions = third.getByLabel('Actions for CF-3', { exact: true })
  await actions.filter({ visible: true }).click({ modifiers: ['ControlOrMeta'] }) // nor does one on its menu
  await expect(writesBoard.getByRole('menu', { name: 'Actions for CF-3' })).toBeVisible() // it opened the menu
  await expect(bar(writesBoard)).toHaveCount(0)
  await writesBoard.keyboard.press('Escape')
  await select(first, second, third)
  await bar(writesBoard).getByText('3 selected').waitFor({ timeout: TIMEOUT })
  await expect(first.getByRole('link', { name: /, selected$/ })).toBeVisible()
  await expect(second.getByRole('link', { name: /, selected$/ })).toBeVisible()
  await expect(third.getByRole('link', { name: /, selected$/ })).toBeVisible()
  expect(
    await writesBoard.evaluate(() => document.querySelectorAll('li[aria-selected]').length),
  ).toBe(0)
  await select(second)
  await bar(writesBoard).getByText('2 selected').waitFor({ timeout: TIMEOUT })
  await (await menu(writesBoard, 'CF-3')).getByRole('menuitem', { name: 'Archive' }).click()
  await bar(writesBoard).getByText('1 selected').waitFor({ timeout: TIMEOUT })
  const url = writesBoard.url()
  await writesBoard.keyboard.press('Escape')
  await bar(writesBoard).waitFor({ state: 'hidden', timeout: TIMEOUT })

  await expect(second.getByRole('link', { name: /selected/ })).toHaveCount(0)
  await expect(first.getByRole('link', { name: /selected/ })).toHaveCount(0)
  expect(writesBoard.url()).toBe(url)
  expect(served.ticket('CF-3')).toContain('archived: true')
})

test('e2e_a_bulk_priority_is_undone_for_all', async ({ served, writesBoard }) => {
  await select(card(writesBoard, 'CF-2'), card(writesBoard, 'CF-1', 'second'))
  const tools = bar(writesBoard)
  await tools.getByRole('button', { name: 'Priority' }).click()
  await writesBoard
    .getByRole('menu', { name: 'Set priority of selected' })
    .getByRole('menuitem', { name: 'low', exact: true })
    .click()
  const notice = toasts(writesBoard)
  await notice.getByText('Set low priority on 2 tickets').waitFor({ timeout: TIMEOUT })
  const changed = [served.ticket('CF-2'), served.ticket('CF-1', 'second')]
  await tools.waitFor({ state: 'hidden', timeout: TIMEOUT })
  await notice.getByRole('button', { name: 'Undo' }).click()
  await expect.poll(() => served.ticket('CF-1', 'second')).toContain('priority: medium')

  expect(changed.every((text) => text.includes('priority: low'))).toBe(true)
  expect(served.ticket('CF-2')).not.toContain('priority')
})

test('e2e_a_refused_bulk_move_changes_nothing', async ({ served, writesBoard }) => {
  const before = [served.ticket('CF-2'), served.ticket('CF-3')]
  await select(card(writesBoard, 'CF-2'), card(writesBoard, 'CF-3'))
  const tools = bar(writesBoard)
  await tools.getByRole('button', { name: 'Move to' }).click()
  await writesBoard
    .getByRole('menu', { name: 'Move selected to' })
    .getByRole('menuitem', { name: 'Review', exact: true })
    .click()
  await toasts(writesBoard)
    .getByText('CF-2 moves one column at a time: Build is next')
    .waitFor({ timeout: TIMEOUT })
  await expect(tools.getByText('2 selected')).toBeVisible()
  const afterRefusal = [served.ticket('CF-2'), served.ticket('CF-3')]
  await tools.getByRole('textbox', { name: 'Add label to selected' }).fill('ops')
  await tools.getByRole('textbox', { name: 'Add label to selected' }).press('Enter')
  await toasts(writesBoard).getByText('Labelled 2 tickets ops').waitFor({ timeout: TIMEOUT })

  expect(afterRefusal).toStrictEqual(before)
  expect(served.ticket('CF-2')).toContain('labels: ops')
  expect(served.ticket('CF-3')).toContain('labels: ops')
})

test('e2e_the_bulk_bar_fits_a_phone', async ({ writesBoard }) => {
  await writesBoard.setViewportSize({ width: 390, height: 844 })
  await select(card(writesBoard, 'CF-2'), card(writesBoard, 'CF-1', 'second'))
  const tools = bar(writesBoard)
  await tools.getByText('2 selected').waitFor({ timeout: TIMEOUT })
  const drawn = await tools.boundingBox()
  expect(drawn?.x).toBeGreaterThanOrEqual(0)
  expect((drawn?.x ?? 0) + (drawn?.width ?? 0)).toBeLessThanOrEqual(390)
  await expect(tools.getByRole('button', { name: 'Clear selection' })).toBeInViewport({ ratio: 1 })
  await expect(tools.getByRole('button', { name: 'Archive' })).toBeInViewport({ ratio: 1 })
})

for (const width of [1600, 390]) {
  test(`e2e_a_refused_bulk_move_closes_its_menu_and_leaves_the_bar_clear_at_${String(width)}`, async ({
    served,
    writesBoard,
  }) => {
    await writesBoard.setViewportSize({ width, height: 844 })
    await select(card(writesBoard, 'CF-2'), card(writesBoard, 'CF-3'))
    const tools = bar(writesBoard)
    await tools.getByRole('button', { name: 'Move to' }).click()
    const moves = writesBoard.getByRole('menu', { name: 'Move selected to' })
    await moves.getByRole('menuitem', { name: 'Review', exact: true }).click()
    const toast = toasts(writesBoard).getByText('CF-2 moves one column at a time')
    await toast.waitFor({ timeout: TIMEOUT })

    await expect(moves).toBeHidden()
    const [barBox, toastBox] = [await tools.boundingBox(), await toast.boundingBox()]
    const apart =
      (toastBox?.y ?? 0) + (toastBox?.height ?? 0) <= (barBox?.y ?? 0) ||
      (barBox?.y ?? 0) + (barBox?.height ?? 0) <= (toastBox?.y ?? 0)
    expect(apart).toBe(true)
    await tools.getByRole('button', { name: 'Archive' }).click()

    await expect.poll(() => served.ticket('CF-2'), { timeout: TIMEOUT }).toContain('archived: true')
  })
}
