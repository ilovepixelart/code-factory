// CF-627: the Inbox on a phone (390 x 844) over the metrics sample (an item waiting in every
// section), served unfollowed so the sample stays as written.

import type { Locator, Page } from '@playwright/test'
import { TIMEOUT, expect, scroller, seedInbox, serve, test, type Served } from './fixtures'

const PHONE = { width: 390, height: 844 }
/** A command with no space to break at, wider than a phone. */
const LONG_COMMAND = `cat ${'src/very/deeply/nested/module/path/'.repeat(4)}file.rs`

/** Serve the metrics sample, changed by `prepare`, with `path` open at a phone's size. */
async function onPhone(
  page: Page,
  path: string,
  prepare: (served: Served) => void,
): Promise<{ served: Served; stop: () => void }> {
  const { served, stop } = await serve('metrics', 'false', false)
  prepare(served)
  await page.setViewportSize(PHONE)
  await page.goto(`${served.url}${path}`)
  await page.getByRole('region', { name: 'Ready for review' }).waitFor({ timeout: TIMEOUT })
  return { served, stop }
}

/** Whether `control` lies whole between the viewport's left and right edges. */
async function across(control: Locator): Promise<boolean> {
  const drawn = await control.boundingBox()
  return drawn !== null && drawn.x >= 0 && drawn.x + drawn.width <= PHONE.width
}

// CF-627-R3 (CF-627-A1): a question is answered and a permission request allowed at a phone's
// width, every control inside the screen and nothing scrolling sideways.
test('e2e_the_inbox_answers_from_a_phone', async ({ page, served }) => {
  seedInbox(served, {
    ticket: 'CF-1',
    question: { text: 'Which colour?' },
    permission: { id: 'aaaaaaaaaaaa', summary: LONG_COMMAND },
  })
  await page.setViewportSize(PHONE)
  await page.goto(`${served.url}/inbox`)
  const wide = (e: Element) => e.scrollWidth - e.clientWidth
  const questions = page.getByRole('region', { name: 'Questions' })
  const requests = page.getByRole('region', { name: 'Permission requests' })
  const answer = questions.getByRole('button', { name: 'Answer' })
  const [allow, deny] = [
    requests.getByRole('button', { name: 'Allow' }),
    requests.getByRole('button', { name: 'Deny' }),
  ]
  const root = await page.evaluate(() => {
    const html = document.documentElement
    return html.scrollWidth - html.clientWidth
  })

  expect(await scroller(page).evaluate(wide)).toBe(0)
  expect(root).toBe(0)
  for (const control of [answer, allow, deny]) {
    await control.scrollIntoViewIfNeeded()
    expect(await across(control)).toBe(true)
  }

  await questions.getByRole('textbox').fill('Blue')
  await answer.click()
  await allow.click()

  await expect(questions).toBeHidden({ timeout: TIMEOUT })
  await expect(requests).toBeHidden({ timeout: TIMEOUT })
  const ticket = await served.api('GET', '/api/tickets/sample/CF-1')
  expect(ticket.json).toMatchObject({ questions: [{ text: 'Which colour?', answer: 'Blue' }] })
})

// CF-627-R2 (CF-627-A2): a push link names its item after `#`, and the page opens scrolled to it.
test('e2e_a_push_link_opens_the_inbox_at_its_item', async ({ page }) => {
  const ids = Array.from({ length: 8 }, (_, n) => `e2e00000000${String(n)}`)
  const last = ids.at(-1) ?? ''
  const { stop } = await onPhone(page, `/inbox#perm-${last}`, (s) => {
    for (const id of ids) s.writeRequest('CF-7', `ls ${id}`, id)
  })
  try {
    const item = page
      .getByRole('region', { name: 'Permission requests' })
      .getByRole('listitem')
      .filter({ hasText: `ls ${last}` })

    await expect(item).toHaveAttribute('id', `perm-${last}`)
    await expect(item).toBeInViewport()
    expect(await scroller(page).evaluate((e) => e.scrollTop)).toBeGreaterThan(0)
    // Only the page's scroll area moved: the top bar stays on screen.
    const moved = await page.evaluate(() =>
      [document.documentElement, ...document.querySelectorAll('body *')]
        .filter((e) => !e.hasAttribute('data-scroller') && e.scrollTop > 0)
        .map((e) => e.tagName),
    )
    expect(moved).toStrictEqual([])
  } finally {
    stop()
  }
})

const LONG_CHOICE =
  'Use the existing relational database with a new table per importer and migrate old rows lazily on first read'
const UNBROKEN_CHOICE = 'x'.repeat(96)

// docs/design.md Long text: a long choice wraps inside its button and the card stays on the screen.
for (const [name, choice, several] of [
  ['a_long_choice', LONG_CHOICE, false],
  ['an_unbroken_choice', UNBROKEN_CHOICE, false],
  ['an_unbroken_choice_to_tick', UNBROKEN_CHOICE, true],
] as const) {
  test(`e2e_the_inbox_keeps_${name}_inside_a_phone`, async ({ page, served }) => {
    seedInbox(served, {
      ticket: 'CF-1',
      question: {
        text: 'Which colour?',
        several,
        choices: [{ text: choice }, { text: 'Postgres' }],
      },
    })
    await page.setViewportSize(PHONE)
    await page.goto(`${served.url}/inbox`)
    const questions = page.getByRole('region', { name: 'Questions' })
    const long = questions.getByText(choice, { exact: true })

    await expect(long).toBeVisible({ timeout: TIMEOUT })
    expect(await scroller(page).evaluate((e) => e.scrollWidth - e.clientWidth)).toBe(0)
    expect(await across(long)).toBe(true)
    expect(await across(questions.getByText('Postgres', { exact: true }))).toBe(true)
    expect(await across(questions.getByRole('textbox'))).toBe(true)
  })
}

const TOUCH_TARGET = 44
const FINE_ACTION_HEIGHT = 32

const ACTIONS = /^(Answer|Always allow|Open ticket|Restart agent)$/

/** The heights of the Inbox's row actions, buttons and links drawn as buttons. */
async function actionHeights(page: Page): Promise<number[]> {
  const main = page.getByRole('main')
  const actions = [
    ...(await main.getByRole('button', { name: ACTIONS }).all()),
    ...(await main.getByRole('link', { name: ACTIONS }).all()),
  ]
  return Promise.all(actions.map(async (a) => (await a.boundingBox())?.height ?? 0))
}

// docs/design.md Touch targets: on a coarse pointer a row action is 44 px tall.
test('e2e_the_inbox_row_actions_are_44px_tall_on_touch', async ({ browser }) => {
  const { served, stop } = await serve('metrics', 'false', false)
  const context = await browser.newContext({ hasTouch: true, isMobile: true, viewport: PHONE })
  try {
    const page = await context.newPage()
    await page.goto(`${served.url}/inbox`)
    await page.getByRole('region', { name: 'Ready for review' }).waitFor({ timeout: TIMEOUT })
    const heights = await actionHeights(page)

    expect(heights.length).toBeGreaterThan(1)
    expect(Math.min(...heights)).toBeGreaterThanOrEqual(TOUCH_TARGET)
  } finally {
    await context.close()
    stop()
  }
})

// A fine pointer keeps the compact desktop size.
test('e2e_the_inbox_row_actions_keep_their_size_on_a_fine_pointer', async ({ page }) => {
  const { stop } = await onPhone(page, '/inbox', () => undefined)
  try {
    expect(new Set(await actionHeights(page))).toStrictEqual(new Set([FINE_ACTION_HEIGHT]))
  } finally {
    stop()
  }
})
