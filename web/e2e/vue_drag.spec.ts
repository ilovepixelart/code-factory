// CF-222 acceptance flows: dragging cards on the Vue board, served by the server over the
// writes sample state.

import type { Locator, Page, Route } from '@playwright/test'
import {
  TIMEOUT,
  card,
  cards,
  expect,
  present,
  test,
  toasts,
  holdPoll,
  type Served,
} from './fixtures'
import { OWNER_COOKIE } from './owner'
import { STAGE_LABELS } from '../src/lib/board'

const COLUMN = new RegExp(`^(${Object.values(STAGE_LABELS).join('|')})$`)

function column(page: Page, label: string): Locator {
  return page.getByRole('region', { name: label, exact: true })
}

/** A column's card list. */
function cardsOf(page: Page, label: string): Locator {
  return column(page, label).getByRole('list', { name: `${label} tickets`, exact: true })
}

/** Take hold of a card by its body, away from its menu and links; where the pointer holds it. */
async function press(page: Page, item: Locator): Promise<{ x: number; y: number }> {
  const box = await item.boundingBox()
  expect(box).not.toBeNull()
  const { x, y, height } = present(box, 'the card')
  const at = { x: x + 20, y: y + height - 12 }
  await page.mouse.move(at.x, at.y)
  await page.mouse.down()
  // CF-840-R3: a card lifts once its press is held 250 ms, when Sortable marks it chosen.
  await expect(item).toHaveClass(/sortable-chosen/)
  return at
}

/** Drag a card with the pointer onto `target`, over its middle or just below it. The target is
 *  measured once the drag has begun, since folded columns open then and the others narrow. */
async function drag(page: Page, item: Locator, target: Locator, below = false): Promise<void> {
  const at = await press(page, item)
  await page.mouse.move(at.x, at.y + 10, { steps: 5 })
  const folded = page.getByRole('main').getByRole('button', { name: COLUMN, expanded: false })
  await expect(folded).toHaveCount(0)
  const box = await target.boundingBox()
  expect(box).not.toBeNull()
  const drawn = present(box, 'the target')
  const y = drawn.y + (below ? drawn.height + 30 : drawn.height / 2)
  await page.mouse.move(drawn.x + drawn.width / 2, y, { steps: 20 })
  await page.mouse.up()
}

async function order(page: Page, label: string): Promise<string[]> {
  const found: string[] = []
  for (const item of await cards(column(page, label)).all()) {
    found.push(
      `${String(await item.getAttribute('data-repository'))}/${String(await item.getAttribute('data-ticket'))}`,
    )
  }
  return found
}

test('e2e_a_card_dragged_to_another_column_moves', async ({ served, writesBoard }) => {
  await drag(writesBoard, card(writesBoard, 'CF-3'), cardsOf(writesBoard, 'Spec'))
  const notice = toasts(writesBoard)
  await notice.getByText('Moved CF-3 to Spec').waitFor({ timeout: TIMEOUT })
  await expect.poll(() => served.ticket('CF-3').includes('stage: spec')).toBe(true)
  const moved = card(column(writesBoard, 'Spec'), 'CF-3')
  await moved.waitFor({ timeout: TIMEOUT })

  await expect(notice.getByRole('button', { name: 'Undo' })).toBeVisible()
  // The moved card can still be taken hold of: the pointer over it shows the grab cursor.
  await expect(moved).toHaveCSS('cursor', 'grab')
})

// CF-840-R2: a click on a card's title that drifts a few pixels opens the ticket, and the card
// stays in its column with no move sent.
test('e2e_a_click_opens_the_ticket_and_leaves_the_card', async ({ writesBoard }) => {
  const moves: string[] = []
  writesBoard.on('request', (r) => {
    if (r.url().endsWith('/move')) moves.push(r.url())
  })
  const title = card(writesBoard, 'CF-3').getByRole('link', { name: 'Declared' })
  const box = present(await title.boundingBox(), 'the title')
  await writesBoard.mouse.move(box.x + 5, box.y + box.height / 2)
  await writesBoard.mouse.down()
  await writesBoard.mouse.move(box.x + 8, box.y + box.height / 2, { steps: 3 })
  await writesBoard.mouse.up()

  // A click on the board opens the ticket in its panel.
  await writesBoard.getByRole('form', { name: 'Edit ticket CF-3' }).waitFor({ timeout: TIMEOUT })
  await expect(card(column(writesBoard, 'Build'), 'CF-3')).toHaveCount(1)
  expect(moves).toStrictEqual([])
})

test('e2e_a_refused_drop_puts_the_card_back', async ({ served, writesBoard }) => {
  const before = served.ticket('CF-2')
  await holdPoll(writesBoard)
  await drag(writesBoard, card(writesBoard, 'CF-2'), cardsOf(writesBoard, 'Build'))
  await toasts(writesBoard)
    .getByText(
      'CF-2 needs a branch before Build: start an agent on it, or run code-factory start CF-2',
    )
    .waitFor({ timeout: TIMEOUT })
  await card(column(writesBoard, 'Spec'), 'CF-2').waitFor({ timeout: TIMEOUT })

  await expect(card(column(writesBoard, 'Build'), 'CF-2')).toHaveCount(0)
  expect(served.ticket('CF-2')).toBe(before)
})

test('e2e_a_drop_within_a_column_ranks_it', async ({ served, writesBoard }) => {
  const other = card(writesBoard, 'CF-1', 'second')
  await expect.poll(async () => (await order(writesBoard, 'Spec'))[0]).toMatch(/^sample\//)
  const refreshed = boardAfterMove(writesBoard)
  await drag(writesBoard, card(writesBoard, 'CF-2'), other, true)
  await expect.poll(() => served.ticket('CF-1', 'second').includes('rank: 1')).toBe(true)
  await refreshed

  await expect
    .poll(() => order(writesBoard, 'Spec'))
    .toStrictEqual(['sample/CF-1', 'second/CF-1', 'sample/CF-2'])
  // Each repository's cards are ranked in the dropped order from 1 (rank_tickets).
  expect(served.ticket('CF-2')).toContain('rank: 2')
})

/** Settle once the board is read after a drop's move is answered: it then draws the server's
 *  order, no longer the one the drag left in the page. */
async function boardAfterMove(page: Page): Promise<void> {
  await page.waitForResponse((r) => r.url().endsWith('/move'), { timeout: TIMEOUT })
  const read = await page.waitForResponse((r) => r.url().endsWith('/api/board'), {
    timeout: TIMEOUT,
  })
  await read.finished()
}

async function create(served: Served, title: string): Promise<void> {
  const answer = await fetch(`${served.url}/api/tickets`, {
    method: 'POST',
    headers: { Cookie: OWNER_COOKIE, 'Content-Type': 'application/json' },
    body: JSON.stringify({ repository: 'sample', title }),
  })
  expect(answer.status).toBe(201)
}

/** The board's poll interval (web/src/lib/live.ts POLL_MS), the only timer of that length on the
 *  tickets page. */
const POLL_MS = 3000

/** Count, from now on, the board's poll ticks the page runs, held or not: a held tick sends no
 *  request, so only its timer shows that it came. */
async function countTicks(page: Page): Promise<void> {
  await page.evaluate((poll) => {
    const spy = window as unknown as { ticks: number }
    const real = window.setTimeout.bind(window)
    spy.ticks = 0
    const counted = (handler: TimerHandler, ms?: number, ...rest: unknown[]): number => {
      if (ms !== poll || typeof handler !== 'function') return real(handler, ms, ...rest)
      return real(
        (...args: unknown[]) => {
          spy.ticks += 1
          ;(handler as (...a: unknown[]) => void)(...args)
        },
        ms,
        ...rest,
      )
    }
    window.setTimeout = counted as typeof window.setTimeout
  }, POLL_MS)
}

function ticks(page: Page): Promise<number> {
  return page.evaluate(() => (window as unknown as { ticks: number }).ticks)
}

test('e2e_the_board_holds_still_during_a_drag', async ({ served, writesBoard }) => {
  const held: Route[] = []
  const polls: string[] = []

  await writesBoard.route('**/api/board', (route) => {
    held.push(route)
  })
  // A poll is on its way when the drag begins.
  await expect.poll(() => held.length).toBeGreaterThan(0)
  await countTicks(writesBoard)
  await press(writesBoard, card(writesBoard, 'CF-3'))
  const box = await column(writesBoard, 'Spec').boundingBox()
  expect(box).not.toBeNull()
  const { x, y } = present(box, 'the Spec column')
  await writesBoard.mouse.move(x + 40, y + 40, { steps: 10 })
  await create(served, 'Made meanwhile')
  await held[0]?.continue()
  await writesBoard.unroute('**/api/board')
  writesBoard.on('request', (r) => {
    if (r.url().includes('/api/board')) polls.push(r.url())
  })
  // The board's next poll comes due while the card is still held.
  await expect.poll(() => ticks(writesBoard), { timeout: TIMEOUT }).toBeGreaterThan(0)
  await expect(writesBoard.getByText('Made meanwhile')).toHaveCount(0)
  const sent = [...polls]
  await writesBoard.mouse.move(x + 5, y - 30, { steps: 5 })
  await writesBoard.mouse.up()
  await writesBoard.getByText('Made meanwhile').waitFor({ timeout: TIMEOUT })

  expect(sent).toStrictEqual([])
})

test('e2e_a_card_dragged_up_its_column_takes_that_place', async ({ served, writesBoard }) => {
  const first = card(writesBoard, 'CF-2')
  await expect.poll(async () => (await order(writesBoard, 'Spec'))[0]).toBe('sample/CF-2')
  const refreshed = boardAfterMove(writesBoard)
  await drag(writesBoard, card(writesBoard, 'CF-1', 'second'), first)
  await expect.poll(() => served.ticket('CF-1', 'second').includes('rank: 1')).toBe(true)
  await refreshed

  await expect
    .poll(() => order(writesBoard, 'Spec'))
    .toStrictEqual(['second/CF-1', 'sample/CF-2', 'sample/CF-1'])
})

test('e2e_a_lane_takes_only_its_own_cards', async ({ served, writesBoard }) => {
  await writesBoard.goto(`${served.url}/tickets?lanes=repository`)
  const otherLane = column(writesBoard, 'Spec').getByRole('list', {
    name: 'second, Spec tickets',
    exact: true,
  })
  await otherLane.waitFor({ timeout: TIMEOUT })
  const before = served.ticket('CF-3')
  const moves: string[] = []
  writesBoard.on('request', (r) => {
    if (r.url().endsWith('/move')) moves.push(r.url())
  })
  await drag(writesBoard, card(writesBoard, 'CF-3'), otherLane)
  // A move would be sent as the card drops; the board's next read after the drop shows the
  // server's state.
  await (
    await writesBoard.waitForResponse((r) => r.url().endsWith('/api/board'), { timeout: TIMEOUT })
  ).finished()

  expect(moves).toStrictEqual([])
  expect(served.ticket('CF-3')).toBe(before)
  await expect(card(column(writesBoard, 'Build'), 'CF-3')).toHaveCount(1)
  await expect(card(otherLane, 'CF-3')).toHaveCount(0)
})

test('e2e_folded_columns_open_to_take_a_drop', async ({ served, writesBoard }) => {
  const review = column(writesBoard, 'Review')
  const foldedBefore = (await review.getAttribute('data-collapsed')) !== null
  const before = served.ticket('CF-3')
  await press(writesBoard, card(writesBoard, 'CF-3'))
  await writesBoard.mouse.move(700, 400, { steps: 10 })
  await expect(review, 'opened during the drag').not.toHaveAttribute('data-collapsed')
  const target = await cardsOf(writesBoard, 'Review').boundingBox()
  expect(target).not.toBeNull()
  const { x, y, width } = present(target, 'the Review cards')
  await writesBoard.mouse.move(x + width / 2, y + 30, { steps: 15 })
  await writesBoard.mouse.up()
  // CF-3 has no spec, so the drop is refused and the emptied column folds again.
  await toasts(writesBoard)
    .getByText(/^CF-3 needs .* before Review(: .*)?$/)
    .waitFor({ timeout: TIMEOUT })
  await expect.poll(async () => (await review.getAttribute('data-collapsed')) !== null).toBe(true)

  expect(foldedBefore).toBe(true)
  expect(served.ticket('CF-3')).toBe(before)
})
