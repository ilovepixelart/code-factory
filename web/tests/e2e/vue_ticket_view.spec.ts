// CF-251 acceptance flows: the ticket view, as a page and as the board's side panel, over the
// writes sample state. Each check runs in both views unless it names one.

import type { Locator, Page } from '@playwright/test'
import { writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { STAGE_LABELS } from '../../src/lib/board'
import {
  OPEN_OVERLAY,
  TIMEOUT,
  box,
  card,
  expect,
  git,
  scroller,
  settle,
  test,
  Served,
  boardLoaded,
} from './fixtures'
import { OWNER_COOKIE } from './owner'

type View = 'page' | 'panel'
const VIEWS: View[] = ['page', 'panel']
const LONG_TITLE =
  'A ticket title long enough to need a second line in every view of the board, written out ' +
  'here to reach well past one line of the field'
const LONG_BRANCH =
  'feat/CF-2-a-branch-name-long-enough-that-the-code-property-field-cannot-hold-it'
const STAGE_LABEL = new RegExp(`^(${Object.values(STAGE_LABELS).join('|')})$`)

// CF-1020-R1: the panel's slide held at its start until `open` finishes it.
test.use({ held: true })

async function patch(served: Served, id: string, body: object): Promise<void> {
  const answer = await fetch(`${served.url}/api/tickets/sample/${id}`, {
    method: 'PATCH',
    headers: { Cookie: OWNER_COOKIE, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  expect(answer.status, await answer.text()).toBe(200)
}

/** Declare CF-2's column in its card, as a person moving it by hand past its evidence would. */
function declare(served: Served, stage: string): void {
  writeFileSync(
    join(served.root, '.code-factory', 'tickets', 'CF-2', 'ticket.md'),
    `---\nid: CF-2\ntitle: Bare\nstage: ${stage}\n---\n`,
  )
}

/** The ticket's form once drawn, as a page or in the board's panel, which may still slide in. */
async function reveal(page: Page, served: Served, view: View, id = 'CF-2'): Promise<Locator> {
  if (view === 'page') {
    await page.goto(`${served.url}/tickets/sample/${id}`)
  } else {
    await page.goto(`${served.url}/tickets`)
    await card(page, id).getByRole('paragraph').getByRole('link').click()
  }
  const form = page.getByRole('form', { name: `Edit ticket ${id}` })
  await form.waitFor({ timeout: TIMEOUT })
  await form.getByRole('region', { name: 'Status' }).waitFor({ timeout: TIMEOUT })
  return form
}

/** The ticket's form, opened as a page or in the board's panel, at rest. */
async function open(page: Page, served: Served, view: View, id = 'CF-2'): Promise<Locator> {
  const form = await reveal(page, served, view, id)
  // The panel slides in; a box measured mid-slide is not where it rests.
  await settle(page, OPEN_OVERLAY)
  return form
}

/** The box a view scrolls in: the app's main area for the page, the panel's dialog. */
function frame(page: Page, view: View): Locator {
  return view === 'page' ? scroller(page) : page.getByRole('dialog')
}

function overflows(box: Locator): Promise<boolean> {
  return box.evaluate(
    (e) => e.scrollWidth > e.clientWidth && getComputedStyle(e).textOverflow === 'ellipsis',
  )
}

// Each check's body, run on the page and then in the panel by its named test below.
const e2e_a_long_title_wraps_once = async (
  view: View,
  served: Served,
  writesBoard: Page,
): Promise<void> => {
  await patch(served, 'CF-2', { title: LONG_TITLE })
  const form = await open(writesBoard, served, view)
  const title = form.getByRole('textbox', { name: 'Title' })
  const [height, scrolled, line] = await title.evaluate((e) => [
    e.clientHeight,
    e.scrollHeight,
    parseFloat(getComputedStyle(e).lineHeight),
  ])

  await expect(title).toHaveValue(LONG_TITLE)
  expect(scrolled).toBeLessThanOrEqual(height)
  expect(height).toBeGreaterThan(line * 1.5)
  await title.press('End')
  await title.pressSequentially(' too')
  await title.press('Enter')
  await expect(title).toHaveValue(`${LONG_TITLE} too`)
  await expect
    .poll(() => served.ticket('CF-2'), { timeout: TIMEOUT })
    .toContain(`${LONG_TITLE} too`)
  if (view === 'page') {
    await expect(writesBoard.getByRole('navigation', { name: 'Breadcrumb' })).toHaveText(
      /^\s*Tickets\s+\/\s+CF-2\s*$/,
      { useInnerText: true },
    )
  }
}

const e2e_the_ticket_page_scrolls_once = async (
  view: View,
  served: Served,
  writesBoard: Page,
): Promise<void> => {
  git(served.root, 'branch', '-f', 'feat/CF-2')
  await patch(served, 'CF-2', { description: 'A line.\n\n'.repeat(80), branch: 'feat/CF-2' })
  const form = await open(writesBoard, served, view)
  const pane = frame(writesBoard, view)
  const scrollers = await pane.evaluate(
    (root) =>
      [root, ...root.querySelectorAll('*')].filter((e) => {
        const y = getComputedStyle(e).overflowY
        return (y === 'auto' || y === 'scroll') && e.scrollHeight > e.clientHeight + 1
      }).length,
  )
  const footer = await box(form.getByTestId('ticket-footer'))
  const bottom = await box(pane)
  // Scrolled to its end, the last section clears the footer instead of running under it.
  await pane.evaluate((root) => {
    for (const e of [root, ...root.querySelectorAll('*')]) e.scrollTop = e.scrollHeight
  })
  const last = await box(form.getByRole('region', { name: 'Activity' }))
  const resting = await box(form.getByTestId('ticket-footer'))

  expect(scrollers).toBe(1)
  expect(Math.abs(footer.y + footer.height - (bottom.y + bottom.height))).toBeLessThanOrEqual(1)
  expect(last.y + last.height).toBeLessThanOrEqual(resting.y + 1)
}

const e2e_a_long_code_value_ends_in_an_ellipsis = async (
  view: View,
  served: Served,
  writesBoard: Page,
): Promise<void> => {
  git(served.root, 'branch', '-f', LONG_BRANCH)
  await patch(served, 'CF-2', { branch: LONG_BRANCH })
  const form = await open(writesBoard, served, view)
  const branch = form.getByLabel('Branch')

  await expect(branch).toHaveValue(LONG_BRANCH)
  expect(await overflows(branch)).toBe(true)
  await expect(branch).toHaveAttribute('title', LONG_BRANCH)
}

const e2e_the_stage_line_agrees_with_the_column = async (
  view: View,
  served: Served,
  writesBoard: Page,
): Promise<void> => {
  declare(served, 'merged')
  const form = await open(writesBoard, served, view)
  const status = form.getByRole('region', { name: 'Status' })

  const text = await form.innerText()

  expect(await status.innerText()).toContain('In Merged')
  expect(text).not.toContain('Where the board looks')
  await expect(form.getByLabel('Evidence steps')).toHaveCount(0)
}

const e2e_the_stage_shows_once = async (
  view: View,
  served: Served,
  writesBoard: Page,
): Promise<void> => {
  const before = await (await open(writesBoard, served, view)).innerText()
  declare(served, 'spec')
  const after = await (await open(writesBoard, served, view)).innerText()

  for (const text of [before, after]) {
    expect(text).not.toContain('placed by its evidence')
    expect(text).not.toContain('moved here by hand')
  }
}

const e2e_a_link_stays_inside_its_card = async (
  view: View,
  served: Served,
  writesBoard: Page,
): Promise<void> => {
  await patch(served, 'CF-1', { title: `${LONG_TITLE} ${LONG_TITLE}` })
  await patch(served, 'CF-2', { parent: 'CF-1' })
  const form = await open(writesBoard, served, view)
  const links = form.getByRole('region', { name: 'Links' })
  const link = links.getByRole('list', { name: 'Parent' }).getByRole('link', { name: /^CF-1/ })
  const [id, title, chip] = [
    link.getByText('CF-1', { exact: true }),
    link.getByText(`${LONG_TITLE} ${LONG_TITLE}`, { exact: true }),
    link.getByText(STAGE_LABEL),
  ]
  const line = await id.evaluate((e) => parseFloat(getComputedStyle(e).lineHeight))
  const card = await box(links)
  const badge = await box(chip)

  expect((await box(id)).height).toBeLessThan(line * 1.5)
  expect(await overflows(title)).toBe(true)
  expect(badge.x).toBeGreaterThanOrEqual(card.x)
  expect(badge.x + badge.width).toBeLessThanOrEqual(card.x + card.width)
}

const e2e_the_footer_lines_up_with_the_columns = async (
  view: View,
  served: Served,
  writesBoard: Page,
): Promise<void> => {
  const form = await open(writesBoard, served, view)
  const footer = await box(form.getByTestId('ticket-footer'))
  const whole = await box(form)
  // The footer's first action (New child ticket, CF-817) starts on the content column.
  const icon = await box(
    form.getByTestId('ticket-footer').getByRole('button', { name: 'New child ticket' }),
  )
  const title = await box(form.getByRole('textbox', { name: 'Title' }))

  expect(Math.abs(footer.width - whole.width)).toBeLessThanOrEqual(1)
  expect(Math.abs(icon.x - title.x)).toBeLessThanOrEqual(1)
}

test('e2e_a_long_title_wraps_once', async ({ served, writesBoard }) => {
  for (const view of VIEWS) await e2e_a_long_title_wraps_once(view, served, writesBoard)
})

test('e2e_the_ticket_page_scrolls_once', async ({ served, writesBoard }) => {
  for (const view of VIEWS) await e2e_the_ticket_page_scrolls_once(view, served, writesBoard)
})

test('e2e_a_long_code_value_ends_in_an_ellipsis', async ({ served, writesBoard }) => {
  for (const view of VIEWS)
    await e2e_a_long_code_value_ends_in_an_ellipsis(view, served, writesBoard)
})

test('e2e_the_stage_line_agrees_with_the_column', async ({ served, writesBoard }) => {
  for (const view of VIEWS)
    await e2e_the_stage_line_agrees_with_the_column(view, served, writesBoard)
})

test('e2e_the_stage_shows_once', async ({ served, writesBoard }) => {
  for (const view of VIEWS) await e2e_the_stage_shows_once(view, served, writesBoard)
})

test('e2e_a_link_stays_inside_its_card', async ({ served, writesBoard }) => {
  for (const view of VIEWS) await e2e_a_link_stays_inside_its_card(view, served, writesBoard)
})

test('e2e_the_footer_lines_up_with_the_columns', async ({ served, writesBoard }) => {
  for (const view of VIEWS)
    await e2e_the_footer_lines_up_with_the_columns(view, served, writesBoard)
})

/** The narrow panel's stacking, every box read at one moment so a slide moves them together. */
async function stacking(form: Locator) {
  const row = form.getByRole('region', { name: 'Status' })
  const title = await form.getByRole('textbox', { name: 'Title' }).elementHandle()
  const properties = await form.getByRole('complementary').elementHandle()
  return row.evaluate(
    (e, [t, p]) => {
      const [above, side] = [t.getBoundingClientRect(), p.getBoundingClientRect()]
      return {
        below: side.top > above.bottom,
        left: side.left <= above.left,
        fits: e.scrollWidth <= e.clientWidth,
      }
    },
    [title, properties] as const,
  )
}

// CF-866-R1: the slide is held at its start, the state a loaded machine left it in when a wait
// for its end gave up; the stacking holds at every point of the slide, so nothing waits for it.
test('e2e_a_narrow_panel_stacks_its_columns', async ({ served, browser }) => {
  const context = await browser.newContext({ viewport: { width: 720, height: 800 } })
  try {
    const page = await context.newPage()
    await page.goto(`${served.url}/tickets`)
    await boardLoaded(page)
    const cdp = await context.newCDPSession(page)
    await cdp.send('Animation.enable')
    await cdp.send('Animation.setPlaybackRate', { playbackRate: 0 })
    const form = await reveal(page, served, 'panel')

    await expect
      .poll(() => stacking(form), { timeout: TIMEOUT })
      .toStrictEqual({ below: true, left: true, fits: true })
  } finally {
    await context.close()
  }
})

// The form's body is inset once: by the page's own gutter on a phone, and by the wider inset of a
// desktop window from the `md` breakpoint up. The panel has no gutter of its own, so it keeps 16 px.
test('e2e_the_ticket_form_is_not_inset_twice_on_a_phone', async ({ served, browser }) => {
  const measure = async (width: number, view: View) => {
    const context = await browser.newContext({ viewport: { width, height: 900 } })
    try {
      const page = await context.newPage()
      const form = await reveal(page, served, view)
      await settle(page, OPEN_OVERLAY)
      const title = await box(form.getByLabel('Title'))
      const edge = await box(form)
      return { title, edge }
    } finally {
      await context.close()
    }
  }

  const phone = await measure(390, 'page')
  const wide = await measure(1600, 'page')
  const drawer = await measure(390, 'panel')

  expect(phone.title.x).toBeCloseTo(phone.edge.x, 0)
  expect(phone.title.width).toBeGreaterThanOrEqual(340)
  // Measured before the inset changed: the desktop position and width are as they were.
  expect([wide.title.x - wide.edge.x, wide.title.width]).toStrictEqual([28, 1020])
  expect(drawer.title.x - drawer.edge.x).toBeCloseTo(16, 0)
})
