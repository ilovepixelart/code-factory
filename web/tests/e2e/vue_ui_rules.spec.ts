// CF-338: the rules of docs/ui.md a person meets on the served board, each named for its rule;
// reading over the api sample state, changing over the writes sample state.

import { execFileSync } from 'node:child_process'
import { existsSync, mkdirSync, readFileSync, rmSync, utimesSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import type { Locator, Page } from '@playwright/test'
import { STAGE_LABELS } from '../../src/lib/board'
import {
  BINARY,
  PRIMARY,
  TIMEOUT,
  box,
  card,
  expect,
  git,
  seedInbox,
  serve,
  settle,
  sidebar,
  test,
  boardLoaded,
  type Served,
} from './fixtures'

function column(page: Page, label: string) {
  return page.getByRole('region', { name: label, exact: true })
}

async function board(page: Page, served: Served): Promise<void> {
  await page.goto(`${served.url}/tickets`)
  await boardLoaded(page)
}

const STAGE_NAME = new RegExp(`^(${Object.values(STAGE_LABELS).join('|')})$`)

/** The widths of the board's open columns, and whether the board scrolls sideways. */
async function layout(page: Page) {
  const columns = page.getByRole('region', { name: STAGE_NAME })
  const open = columns.filter({
    has: page.getByRole('heading').getByRole('button', { expanded: true }),
  })
  return {
    widths: await open.evaluateAll((all) => all.map((c) => c.getBoundingClientRect().width)),
    // The columns' shared parent is the area that pans sideways.
    pans: await columns.evaluateAll((all) => {
      const pan = all[0]?.parentElement
      return pan ? pan.scrollWidth > pan.clientWidth : false
    }),
  }
}

test('e2e_columns_share_the_width_equally_from_a_256_px_floor', async ({ api, page }) => {
  await board(page, api)
  // Empty columns fold by default; open them, last first, so every column takes a share.
  const folded = page.getByRole('main').getByRole('button', { name: STAGE_NAME, expanded: false })
  for (const fold of (await folded.all()).reverse()) await fold.click()
  await expect(folded).toHaveCount(0)
  const wide = await layout(page)
  await page.setViewportSize({ width: 900, height: 700 })
  await expect.poll(async () => (await layout(page)).pans).toBe(true)
  const narrow = await layout(page)

  expect(wide.widths.length).toBeGreaterThan(1)
  expect(Math.max(...wide.widths) - Math.min(...wide.widths)).toBeLessThan(1)
  expect(Math.min(...wide.widths)).toBeGreaterThan(256)
  expect(wide.pans).toBe(false)
  expect(narrow.widths.map(Math.round)).toStrictEqual(narrow.widths.map(() => 256))
})

/** A card's right edge, its column's width, and its body's padding and text width. */
async function cardBoxes(scope: Locator) {
  return scope.evaluate((card) => {
    const body = card.querySelector('[data-js-card-body]')
    if (!body) throw new Error('the card has no body')
    const s = getComputedStyle(body)
    const outer = card.getBoundingClientRect()
    const column = card.closest('[data-js-column]')?.getBoundingClientRect().width ?? 0
    const text = body.clientWidth - parseFloat(s.paddingLeft) - parseFloat(s.paddingRight)
    return { right: outer.right, column, text, padding: parseFloat(s.paddingRight) }
  })
}

test('e2e_a_card_gives_12_px_more_of_its_column_to_its_text', async ({ api, page }) => {
  await board(page, api)
  const { column: width, text } = await cardBoxes(card(page, 'CF-2'))

  // On main a column holds a card's text in its width less 51 px: column border 2, list inset
  // 8, scrollbar gutter 11, card border 2, card padding 28.
  expect(width - text).toBeLessThanOrEqual(51 - 12)
})

test('e2e_the_priority_sits_against_the_cards_right_edge', async ({ api, page }) => {
  await board(page, api)
  const high = card(page, 'CF-2')
  const priority = high.getByText('high', { exact: true })
  const [outer, mark] = [await cardBoxes(high), await box(priority)]

  // The card's 1 px border, then its body padding.
  expect(outer.right - (mark.x + mark.width)).toBeLessThanOrEqual(outer.padding + 1)
})

test('e2e_a_column_scrollbar_is_thin_against_its_cards_and_shows_only_on_hover', async ({
  api,
  page,
}) => {
  await board(page, api)
  const frd = column(page, 'Spec')
  const scroll = frd.getByRole('list', { name: 'Spec tickets', exact: true })
  const style = () =>
    scroll.evaluate((e) => {
      const s = getComputedStyle(e)
      return {
        width: s.scrollbarWidth,
        gutter: s.scrollbarGutter,
        padding: s.paddingRight,
        colour: s.scrollbarColor,
      }
    })
  await page.mouse.move(1, 1)
  const rest = await style()
  await frd.hover()
  await expect.poll(async () => (await style()).colour).not.toBe(rest.colour)
  const hovered = await style()

  expect(rest).toStrictEqual({
    width: 'thin',
    gutter: 'stable',
    padding: '0px',
    colour: 'rgba(0, 0, 0, 0) rgba(0, 0, 0, 0)',
  })
  expect(hovered.colour).not.toContain('rgba(0, 0, 0, 0) rgba')
})

test('e2e_enter_on_a_card_title_opens_its_panel', async ({ api, page }) => {
  await board(page, api)
  const title = card(page, 'CF-2').getByRole('link', { name: 'A bug in flight' })
  await title.focus()
  await expect(title).toBeFocused()

  await page.keyboard.press('Enter')

  await expect(page.getByRole('dialog').getByRole('textbox', { name: 'Title' })).toHaveValue(
    'A bug in flight',
  )
  expect(new URL(page.url()).pathname).toBe('/tickets')
})

test('e2e_a_middle_click_on_a_card_title_opens_its_page_in_a_new_tab', async ({ api, page }) => {
  await board(page, api)
  const title = card(page, 'CF-2').getByRole('link', { name: 'A bug in flight' })

  const [opened] = await Promise.all([
    page.context().waitForEvent('page', { timeout: TIMEOUT }),
    title.click({ button: 'middle' }),
  ])

  await expect(opened).toHaveURL(`${api.url}/tickets/sample/CF-2`)
  await expect(opened.getByRole('main').getByRole('textbox', { name: 'Title' })).toHaveValue(
    'A bug in flight',
  )
  expect(new URL(page.url()).pathname).toBe('/tickets')
  await expect(page.getByRole('dialog')).toHaveCount(0)
})

test('e2e_cmd_k_opens_the_command_menu_even_from_a_field', async ({ api, page }) => {
  await page.goto(`${api.url}/tickets/sample/CF-2`)
  const field = page.getByRole('main').getByRole('textbox', { name: 'Title' })
  await field.focus()
  await expect(field).toBeFocused()

  await page.keyboard.press('ControlOrMeta+k')

  await expect(page.getByRole('dialog', { name: 'Command menu' })).toBeVisible()
  await expect(page.getByRole('combobox', { name: 'Search commands' })).toBeFocused()
})

test('e2e_no_shortcut_fires_while_the_person_types', async ({ api, page }) => {
  await board(page, api)
  const box = page.getByRole('searchbox', { name: 'Filter cards' })
  await box.click()

  await page.keyboard.type('gs?[n/')

  await expect(box).toHaveValue('gs?[n/')
  await expect(box).toBeFocused()
  expect(new URL(page.url()).pathname).toBe('/tickets')
  await expect(page.getByRole('dialog', { name: 'Keyboard shortcuts' })).toBeHidden()
  await expect(sidebar(page)).toHaveAttribute('data-state', 'expanded')
  await expect(page.getByRole('dialog')).toHaveCount(0)
})

// On a phone the sidebar is a sheet the header's trigger opens (shadcn-vue's Sidebar).
test('e2e_on_a_phone_the_sidebar_opens_as_a_sheet_with_every_page_link', async ({ api, page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await board(page, api)
  const links = page.getByRole('navigation', { name: 'Pages' })
  await expect(links).toBeHidden()
  await page.getByRole('button', { name: 'Toggle sidebar' }).click()
  const sheet = page.getByRole('dialog', { name: 'Sidebar' })

  await expect(sheet.getByRole('navigation', { name: 'Pages' })).toBeVisible()
  await expect(sheet.getByRole('link', { name: 'Tickets' })).toBeInViewport({ ratio: 1 })
  await expect(sheet.getByRole('link', { name: 'code-factory' })).toBeVisible()
  await expect(sheet.getByRole('button', { name: /^(Dark|Light) theme$/ })).toBeInViewport()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
})

test('e2e_on_a_phone_the_current_page_link_is_in_view_in_the_navigation', async ({ api, page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(`${api.url}/team`)
  await page.getByRole('button', { name: 'Toggle sidebar' }).click()
  const links = page.getByRole('dialog', { name: 'Sidebar' }).getByRole('navigation')
  const current = links.getByRole('link', { name: 'Team', exact: true })
  await expect(current).toHaveAttribute('aria-current', 'page')

  await expect(current).toBeInViewport({ ratio: 1 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
})

test('e2e_the_theme_button_is_named_by_the_words_it_shows', async ({ api, page }) => {
  await board(page, api)
  const shown = page.getByRole('button', { name: 'Dark theme', exact: true })

  await expect(shown).toHaveText('Dark theme')
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('button', { name: 'Toggle sidebar' }).click()
  await expect(
    page.getByRole('dialog', { name: 'Sidebar' }).getByRole('button', { name: 'Dark theme' }),
  ).toBeVisible()
})

test('e2e_n_opens_exactly_one_new_ticket_dialog_on_the_team_page_and_the_board', async ({
  api,
  page,
}) => {
  await page.goto(`${api.url}/team`)
  await expect(page.getByRole('heading', { name: 'Team', level: 1 })).toBeVisible({
    timeout: TIMEOUT,
  })
  await page.keyboard.press('n')
  await expect(page.getByRole('dialog', { name: 'New ticket' })).toHaveCount(1)
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)

  await board(page, api)
  await page.keyboard.press('n')

  await expect(page.getByRole('dialog', { name: 'New ticket' })).toHaveCount(1)
})

// The logo is the product's mark, the same size in the open and the folded sidebar, and the
// favicon is the file the page links.
test('e2e_the_logo_is_the_mark_in_the_open_and_the_folded_sidebar', async ({ api, page }) => {
  await board(page, api)
  const logo = page.getByRole('link', { name: 'code-factory', exact: true })
  const mark = logo.getByTestId('app-mark')
  await expect(logo).toHaveText('code-factory')
  const open = await box(mark)
  await page.getByRole('button', { name: 'Toggle sidebar' }).click()
  await expect(sidebar(page)).toHaveAttribute('data-state', 'collapsed')
  await settle(page)
  const folded = await box(mark)

  expect(open.width).toBeGreaterThan(0)
  expect([folded.width, folded.height]).toStrictEqual([open.width, open.height])
  expect(
    await page.evaluate(() => document.querySelector('link[rel="icon"]')?.getAttribute('href')),
  ).toBe('/favicon.svg')
})

test('e2e_subagent_work_is_nested_under_its_subagent_and_labelled', async ({ api, page }) => {
  await page.goto(`${api.url}/sessions/s-sub`)
  const entries = page.getByRole('list', { name: 'Entries of turn 1', exact: true })
  const group = entries.getByRole('group', { name: 'Subagent Explore a1' })
  await expect(group).toBeVisible()
  await group.getByTestId('agent-name').click()
  const glob = group.getByRole('listitem').filter({ hasText: 'Glob' })
  const task = entries.getByRole('listitem').filter({ hasText: 'Task' })
  const at = (row: typeof glob) => box(row.getByText(/^\d{2}:\d{2}:\d{2}$/))
  const [nested, main] = await Promise.all([at(glob), at(task)])

  await expect(group).toContainText('Explore')
  await expect(group.getByRole('listitem').filter({ hasText: 'Task' })).toHaveCount(0)
  expect(nested.x).toBeGreaterThan(main.x)
})

test('e2e_attention_is_cleared_by_a_state_change_in_the_ledger_never_by_opening_the_page', async ({
  page,
}) => {
  const { served, stop } = await serve('api', 'false', false)
  try {
    await page.goto(served.url)
    const waiting = page.getByRole('list', { name: 'Waiting on you' })
    const blocked = waiting
      .getByRole('listitem')
      .filter({ has: page.getByText('s-block', { exact: true }) })
    await expect(blocked).toBeVisible()
    await blocked.getByRole('link', { name: 'Open session s-block' }).click()
    await page.getByRole('list', { name: 'Timeline' }).waitFor({ timeout: TIMEOUT })
    await page.goto(`${served.url}/inbox`)
    await page.getByRole('region', { name: 'Waiting sessions' }).waitFor({ timeout: TIMEOUT })
    await page.goto(served.url)
    await expect(blocked).toBeVisible()

    const event = {
      session_id: 's-block',
      hook_event_name: 'PostToolUse',
      tool_name: 'Edit',
      tool_use_id: 't3',
      cwd: served.root,
    }
    execFileSync(BINARY, ['capture'], {
      input: JSON.stringify(event),
      env: { ...process.env, CODE_FACTORY_HOME: served.home },
    })

    await expect(
      page
        .getByRole('list', { name: 'Sessions in sample' })
        .getByRole('listitem')
        .filter({ has: page.getByRole('link', { name: 'Session s-block' }) }),
    ).toBeVisible()
    await expect(blocked).toHaveCount(0)
  } finally {
    stop()
  }
})

test('e2e_a_manual_fold_is_dropped_once_the_card_count_crosses_zero', async ({
  served,
  writesBoard,
}) => {
  const build = column(writesBoard, 'Build')
  await expect(card(build, 'CF-3')).toBeVisible()
  await build.getByRole('button', { name: 'Build' }).click()
  await expect(build).toHaveAttribute('data-collapsed')

  served.editTicket('CF-3', 'stage: build\n', '')
  await expect(build).toHaveAttribute('data-count', '0')
  served.editTicket('CF-3', 'id: CF-3\n', 'id: CF-3\nstage: build\n')

  await expect(build).toHaveAttribute('data-count', '1')
  await expect(build).not.toHaveAttribute('data-collapsed')
})

test('e2e_the_changes_show_at_most_400_lines', async ({ served, writesBoard }) => {
  const root = served.root
  git(root, 'checkout', '-q', '-b', 'feat/CF-2')
  const lines = Array.from({ length: 450 }, (_, n) => `line ${String(n + 1)}`)
  writeFileSync(join(root, 'long.txt'), `${lines.join('\n')}\n`)
  git(root, 'add', 'long.txt')
  git(root, 'commit', '-q', '-m', 'Long')
  git(root, 'checkout', '-q', 'main')
  served.editTicket('CF-2', 'rank: 2\n', 'rank: 2\nbranch: feat/CF-2\n')

  await writesBoard.goto(`${served.url}/tickets/sample/CF-2`)
  const changes = writesBoard.getByRole('region', { name: /^Changes/ })
  const rows = changes.getByRole('table', { name: 'long.txt' }).getByRole('row')

  await expect(rows).toHaveCount(400)
  const texts = await rows.allTextContents()
  expect(texts[0]).toContain('line 1')
  expect(texts.at(-1)).toContain('line 400')
  await expect(changes.getByText('cut at 400 lines')).toBeVisible()
})

test('e2e_a_refused_link_shows_its_reason_in_the_picker', async ({ served, writesBoard }) => {
  await writesBoard.goto(`${served.url}/tickets/sample/CF-1`)
  const section = writesBoard.getByRole('region', { name: 'Links' })
  await section.getByRole('list', { name: 'Children' }).getByText('CF-3').waitFor()
  await section.getByRole('button', { name: 'Link a ticket' }).click()
  await section
    .getByRole('group', { name: 'Link kind' })
    .getByRole('button', { name: 'Parent' })
    .click()
  const find = section.getByRole('combobox', { name: 'Find a ticket by id or title' })
  await find.fill('Declared')
  await expect(section.getByRole('option', { name: /CF-3/ })).toBeVisible()

  await find.press('Enter')

  await expect(section.getByText('parent CF-3 would make a loop')).toBeVisible()
  await expect(section.getByRole('option', { name: /CF-3/ })).toBeVisible()
  expect(served.ticket('CF-1')).not.toContain('parent:')
})

test('e2e_a_released_ticket_is_dated_by_its_release_notes_and_has_no_restore', async ({
  served,
  writesBoard,
}) => {
  const releases = join(served.root, '.code-factory', 'releases')
  mkdirSync(releases, { recursive: true })
  const notes = join(releases, '1.0.0.md')
  writeFileSync(notes, '# 1.0.0\n\n- CF-2: Bare\n')
  const released = new Date('2025-03-15T12:00:00Z')
  utimesSync(notes, released, released)

  await writesBoard.goto(`${served.url}/archive`)
  const table = writesBoard.getByRole('table')
  const archived = (id: string) =>
    table.getByRole('row').filter({ has: writesBoard.getByRole('cell', { name: id, exact: true }) })
  const row = archived('CF-2')
  await expect(row).toBeVisible()
  const handArchived = archived('CF-4')

  await expect(handArchived.getByRole('button', { name: 'Restore CF-4' })).toHaveCount(1)
  await expect(row).toContainText('15 Mar 2025')
  await expect(row.getByRole('button', { name: 'Restore CF-2' })).toHaveCount(0)
  await board(writesBoard, served)
  await expect(card(writesBoard, 'CF-1')).toBeVisible()
  await expect(card(writesBoard, 'CF-2')).toHaveCount(0)
})

const SMALL =
  '---\nkind: rule\ndate: 2026-10-01\nsource: conversation\nwhy: Small rules are read\n---\nKeep every rule small\n'
const TWICE =
  '---\nkind: lesson\ndate: 2026-10-02\nsource: CF-2\nwhy: It cost a run\nguard: \n---\nRun the gate once\n'

async function memoryPage(page: Page, served: Served): Promise<string> {
  const folder = served.writeMemory({
    '2026-10-01-keep-every-rule-small.md': SMALL,
    '2026-10-02-run-the-gate-once.md': TWICE,
  })
  await page.goto(`${served.url}/memory`)
  await page
    .getByRole('region', { name: /^Core\b/ })
    .getByRole('listitem', { name: 'Run the gate once' })
    .waitFor({ timeout: TIMEOUT })
  return folder
}

test('e2e_a_memory_entry_is_edited_in_place', async ({ served, writesBoard }) => {
  const folder = await memoryPage(writesBoard, served)
  const small = writesBoard.getByRole('listitem', { name: 'Keep every rule small' })
  // An entry is a closed row; opening it shows its actions (CF-1171).
  await small.getByText('Keep every rule small').click()
  await small.getByRole('button', { name: 'Edit' }).click()
  const form = writesBoard.getByRole('form', { name: 'Edit the entry' })
  await form.getByRole('textbox', { name: 'Statement' }).fill('Keep every rule short')

  await form.getByRole('button', { name: 'Save and mark reviewed' }).click()

  await expect(
    writesBoard
      .getByRole('region', { name: /^Core\b/ })
      .getByRole('listitem', { name: 'Keep every rule short' }),
  ).toBeVisible()
  expect(readFileSync(join(folder, '2026-10-01-keep-every-rule-small.md'), 'utf8')).toContain(
    '\nKeep every rule short\n',
  )
})

test('e2e_a_memory_entry_is_merged_into_another_in_place', async ({ served, writesBoard }) => {
  const folder = await memoryPage(writesBoard, served)
  const twice = writesBoard.getByRole('listitem', { name: 'Run the gate once' })
  await twice.getByText('Run the gate once').click()
  await twice.getByRole('button', { name: 'Merge' }).click()
  const form = twice.getByRole('form', { name: 'Merge the entry' })
  await form.getByLabel('Merge into').selectOption({ label: 'Keep every rule small' })

  await form.getByRole('button', { name: 'Merge' }).click()

  const history = writesBoard.getByRole('region', { name: /^History\b/ })
  await history.getByRole('heading', { name: /^History\s*,\s*1$/ }).click()
  const merged = history.getByRole('listitem', { name: 'Run the gate once' })
  await expect(merged).toContainText(/merged\s*into "Keep every rule small"/)
  await expect(
    writesBoard.getByRole('region', { name: /^Core\b/ }).getByRole('listitem', {
      name: 'Run the gate once',
    }),
  ).toHaveCount(0)
  expect(existsSync(join(folder, 'retired', '2026-10-02-run-the-gate-once.md'))).toBe(true)
})

test('e2e_the_inbox_lists_the_longest_wait_first_with_the_one_primary_button', async ({
  served,
  writesBoard,
}) => {
  seedInbox(served, { ticket: 'CF-2', question: { text: 'Which colour for CF-2?' } })
  seedInbox(served, { ticket: 'CF-1', question: { text: 'Which size?' } })

  await writesBoard.goto(`${served.url}/inbox`)
  const questions = writesBoard.getByRole('region', { name: 'Questions' })
  const rows = questions.getByRole('listitem')
  await expect(rows).toHaveText([/Which colour for CF-2\?/, /Which size\?/])
  const colour = rows.filter({ hasText: 'Which colour for CF-2?' })
  const size = rows.filter({ hasText: 'Which size?' })
  const primaries = () =>
    writesBoard
      .getByRole('main')
      .getByRole('button')
      .evaluateAll((all, primary) => all.filter((b) => b.matches(primary)).length, PRIMARY)

  await expect(colour.getByRole('textbox')).toHaveAccessibleName('Answer to Which colour for CF-2?')
  await expect(size.getByRole('textbox')).toHaveAccessibleName('Answer to Which size?')
  await expect.poll(primaries).toBe(1)
  await expect(colour.getByRole('button', { name: 'Answer' })).toHaveAttribute(
    'data-variant',
    'default',
  )
  await expect(size.getByRole('button', { name: 'Answer' })).toHaveAttribute(
    'data-variant',
    'secondary',
  )
})

test('e2e_a_review_with_no_known_start_shows_no_age', async ({ served, writesBoard }) => {
  served.editTicket('CF-2', 'rank: 2\n', 'rank: 2\nstage: review\n')
  served.editTicket('CF-3', 'stage: build\n', 'stage: review\n')

  await writesBoard.goto(`${served.url}/inbox`)

  const reviews = writesBoard.getByRole('region', { name: 'Ready for review' })
  await expect(reviews.getByRole('listitem')).toHaveText([
    /^CF-2 Bare$/,
    /^CF-3 Declared\s*\d+(\.\d)?d$/,
  ])
})

test('e2e_a_refused_answer_to_a_request_that_left_shows_the_reason', async ({ page }) => {
  const { served, stop } = await serve('metrics', 'false', false)
  try {
    const id = served.writeRequest('CF-5', 'cargo test --workspace')
    await page.goto(`${served.url}/inbox`)
    const requests = page.getByRole('region', { name: 'Permission requests' })
    const request = requests.getByRole('listitem').filter({ hasText: 'cargo test --workspace' })
    await expect(request).toBeVisible({ timeout: TIMEOUT })

    rmSync(join(served.home, 'permissions', `${id}.json`))
    await request.getByRole('button', { name: 'Allow' }).click()

    await expect(requests).toHaveCount(0)
    await expect(page.getByText('the agent stopped waiting for this answer')).toBeVisible()
  } finally {
    stop()
  }
})

// CF-438: a question answered after the Inbox listed it keeps its first answer.
test('e2e_a_second_answer_from_the_inbox_shows_why_and_keeps_the_first', async ({
  served,
  writesBoard,
}) => {
  seedInbox(served, { ticket: 'CF-1', question: { text: 'Which colour?' } })
  await writesBoard.goto(`${served.url}/inbox`)
  const box = writesBoard.getByRole('textbox', { name: 'Answer to Which colour?' })
  await box.fill('Red')

  const path = '/api/tickets/sample/CF-1'
  const elsewhere = await served.api('POST', `${path}/answers`, {
    document: '',
    index: 0,
    question: 'Which colour?',
    answer: 'Blue',
  })
  expect(elsewhere.status).toBe(200)
  await box.press('Enter')

  await expect(writesBoard.getByText('Which colour? is already answered: Blue')).toBeVisible()
  expect((await served.api('GET', path)).json).toMatchObject({
    questions: [{ text: 'Which colour?', answer: 'Blue' }],
  })
})

test('e2e_a_repository_name_in_a_url_path_is_percent_encoded', async ({ served, writesBoard }) => {
  const other = join(served.root, '..', 'r#x')
  mkdirSync(join(other, '.code-factory', 'tickets', 'RX-1'), { recursive: true })
  writeFileSync(
    join(other, '.code-factory', 'tickets', 'RX-1', 'ticket.md'),
    '---\nid: RX-1\ntitle: Hash folder\n---\n',
  )
  git(other, 'init', '-q', '-b', 'main')
  git(other, 'add', '.')
  git(other, 'commit', '-q', '-m', 'Start')
  execFileSync(BINARY, ['track', other], {
    env: { ...process.env, CODE_FACTORY_HOME: served.home },
  })
  const hashed = card(writesBoard, 'RX-1', 'r#x')
  await writesBoard.reload()
  const title = hashed.getByRole('link', { name: 'Hash folder' })
  await expect(title).toHaveAttribute('href', '/tickets/r%23x/RX-1')

  await writesBoard.goto(`${served.url}/tickets/r%23x/RX-1`)
  const field = writesBoard.getByRole('main').getByRole('textbox', { name: 'Title' })
  await expect(field).toHaveValue('Hash folder')
  await field.fill('Hash folder renamed')
  await field.press('Tab')

  await expect
    .poll(() => readFileSync(join(other, '.code-factory', 'tickets', 'RX-1', 'ticket.md'), 'utf8'))
    .toContain('title: Hash folder renamed')
})
