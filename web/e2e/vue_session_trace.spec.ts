// CF-1384: a session page's timeline as a trace, over a seeded session: bars on the turn's time
// axis, idle gaps, a failed call marked besides its color, a subagent's calls under one row, an
// icon per tool kind, in both themes.

import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import type { Locator, Page } from '@playwright/test'
import {
  TIMEOUT,
  box,
  contrast,
  expect,
  scroller,
  serve,
  test as base,
  drawnIn,
  useTheme,
  type Served,
} from './fixtures'

const SESSION = 's-trace'
const TURN_SECONDS = 700

/** The seeded session's events: a prompt, a 5-minute Read from minute 2, a failed Bash, an
 * Explore subagent with two calls, a 3-minute wait, an Edit and the turn's end at 700 s. */
function seed(served: Served): void {
  const begin = Date.now() / 1000 - 900
  const events: Record<string, unknown>[] = [
    { hook_event_name: 'SessionStart', cwd: served.root, source: 'startup' },
    { at: 0, hook_event_name: 'UserPromptSubmit', prompt: 'Trace it' },
    {
      at: 120,
      hook_event_name: 'PreToolUse',
      tool_name: 'Read',
      tool_use_id: 't1',
      tool_input: { file_path: 'a.rs' },
    },
    { at: 420, hook_event_name: 'PostToolUse', tool_name: 'Read', tool_use_id: 't1' },
    {
      at: 430,
      hook_event_name: 'PreToolUse',
      tool_name: 'Bash',
      tool_use_id: 't2',
      tool_input: { command: 'cargo broken' },
    },
    { at: 431, hook_event_name: 'PostToolUseFailure', tool_name: 'Bash', tool_use_id: 't2' },
    { at: 440, hook_event_name: 'SubagentStart', agent_id: 'a1', agent_type: 'Explore' },
    {
      at: 445,
      hook_event_name: 'PreToolUse',
      agent_id: 'a1',
      tool_name: 'Glob',
      tool_use_id: 't3',
      tool_input: { pattern: '*.py' },
    },
    {
      at: 455,
      hook_event_name: 'PostToolUse',
      agent_id: 'a1',
      tool_name: 'Glob',
      tool_use_id: 't3',
    },
    {
      at: 460,
      hook_event_name: 'PreToolUse',
      agent_id: 'a1',
      tool_name: 'Grep',
      tool_use_id: 't4',
      tool_input: { pattern: 'todo' },
    },
    {
      at: 475,
      hook_event_name: 'PostToolUse',
      agent_id: 'a1',
      tool_name: 'Grep',
      tool_use_id: 't4',
    },
    { at: 480, hook_event_name: 'SubagentStop', agent_id: 'a1', agent_type: 'Explore' },
    {
      at: 660,
      hook_event_name: 'PreToolUse',
      tool_name: 'Edit',
      tool_use_id: 't5',
      tool_input: { file_path: 'b.rs' },
    },
    { at: 662, hook_event_name: 'PostToolUse', tool_name: 'Edit', tool_use_id: 't5' },
    { at: TURN_SECONDS, hook_event_name: 'Stop', last_assistant_message: 'Done' },
  ]
  mkdirSync(join(served.home, 'spool'), { recursive: true })
  const lines = events.map(({ at, ...event }) =>
    JSON.stringify({
      session_id: SESSION,
      _captured_at: begin + ((at as number | undefined) ?? 0),
      ...event,
    }),
  )
  writeFileSync(join(served.home, 'spool', `${SESSION}.jsonl`), `${lines.join('\n')}\n`)
}

const test = base.extend<{ page: Page }, { seeded: Served }>({
  seeded: [
    async ({}, use) => {
      const { served, stop } = await serve('api', 'false', false)
      seed(served)
      await use(served)
      stop()
    },
    { scope: 'worker' },
  ],
  page: async ({ browser, seeded }, use) => {
    const context = await browser.newContext()
    const page = await context.newPage()
    await page.goto(`${seeded.url}/sessions/${SESSION}`)
    await page.getByRole('list', { name: 'Entries of turn 1' }).waitFor({ timeout: TIMEOUT })
    await use(page)
    await context.close()
  },
})

/** A top-level row of the turn's entries holding `text`. */
const rowOf = (page: Page, text: string) =>
  page
    .getByRole('list', { name: 'Entries of turn 1', exact: true })
    .getByRole('listitem')
    .filter({ hasText: text })
/** The icons a row draws, in order, as their sprite addresses. */
// Each icon of a row, as the shapes it draws.
const iconsOf = (row: Locator): Promise<string[]> =>
  row.evaluate((e) => [...e.querySelectorAll('svg')].map((svg) => svg.innerHTML))
const agentOf = (page: Page) => page.getByRole('group', { name: 'Subagent Explore a1' })

test('e2e_a_call_s_bar_stands_at_its_share_of_the_turn_s_axis', async ({ page }) => {
  const row = rowOf(page, 'a.rs')
  const [inner, outer] = [await box(row.getByTestId('bar')), await box(row.getByTestId('track'))]

  expect((inner.x - outer.x) / outer.width).toBeCloseTo(120 / TURN_SECONDS, 2)
  expect(inner.width / outer.width).toBeCloseTo(300 / TURN_SECONDS, 2)
})

test('e2e_an_idle_gap_shows_its_length', async ({ page }) => {
  await expect(page.getByTestId('gap')).toHaveText([/^\s*2m idle\s*$/, /^\s*3m idle\s*$/])
})

test('e2e_a_failed_call_is_marked_on_its_row_and_not_by_color_alone', async ({ page }) => {
  const failed = rowOf(page, 'cargo broken')

  expect(await drawnIn(failed, 'destructive', 'border-left-color')).toBe(true)
  await expect(failed).toContainText('failed')
  // Its status carries an icon a call that did not fail lacks.
  expect(await iconsOf(failed)).toHaveLength((await iconsOf(rowOf(page, 'a.rs'))).length + 1)
  expect(await drawnIn(rowOf(page, 'a.rs'), 'destructive', 'border-left-color')).toBe(false)
})

test('e2e_a_subagent_s_calls_sit_under_one_row_naming_it', async ({ page }) => {
  const group = agentOf(page)
  const summary = group.getByTestId('agent-name')

  await expect(page.getByRole('group', { name: /^Subagent / })).toHaveCount(1)
  await expect(group).toContainText('25.0s')
  await expect(group).toHaveAttribute('data-state', 'closed')
  await summary.click()
  await expect(group).toHaveAttribute('data-state', 'open')
  await expect(group.getByRole('listitem').filter({ hasText: '*.py' })).toHaveCount(1)
  await expect(group.getByRole('listitem').filter({ hasText: 'a.rs' })).toHaveCount(0)
  await summary.click()
  await expect(group.getByText('*.py')).toBeHidden()
})

test('e2e_each_tool_kind_has_its_own_icon', async ({ page }) => {
  const kind = async (row: Locator) => (await iconsOf(row))[0]
  await agentOf(page).getByTestId('agent-name').click()
  const nested = agentOf(page).getByRole('listitem').filter({ hasText: 'todo' })

  // A read, an edit, a command and a search: four kinds, four different icons.
  const kinds = [
    await kind(rowOf(page, 'a.rs')),
    await kind(rowOf(page, 'b.rs')),
    await kind(rowOf(page, 'cargo broken')),
    await kind(nested),
  ]
  expect(new Set(kinds).size).toBe(4)
})

test('e2e_bars_and_markers_keep_their_contrast_in_both_themes', async ({ page }) => {
  for (const theme of ['light', 'dark']) {
    await useTheme(page, theme)
    for (const [name, bar] of [
      ['passed bar', rowOf(page, 'a.rs').getByTestId('bar')],
      ['failed bar', rowOf(page, 'cargo broken').getByTestId('bar')],
      ['subagent bar', agentOf(page).getByTestId('agent-bar')],
    ] as const) {
      expect.soft(await contrast(bar, true), `${theme} ${name}`).toBeGreaterThanOrEqual(3)
    }
    expect
      .soft(await contrast(page.getByText('2m idle')), `${theme} gap`)
      .toBeGreaterThanOrEqual(4.5)
    expect
      .soft(await contrast(rowOf(page, 'cargo broken').getByText('failed')), `${theme} failed`)
      .toBeGreaterThanOrEqual(4.5)
  }
})

test('e2e_a_call_s_payload_button_is_named_for_its_call_and_keeps_its_name', async ({ page }) => {
  const named = /^Input and output of call \d+$/
  const row = rowOf(page, 'a.rs')
  const name = await row.getByRole('button', { name: named }).getAttribute('aria-label')
  const control = page.getByRole('button', { name: name ?? '', exact: true })

  await expect(control).toHaveAttribute('aria-expanded', 'false')
  await control.click()
  await expect(control).toHaveAttribute('aria-expanded', 'true')
  await expect(control).toHaveText(/Input and output/)
  await expect(page.getByRole('region', { name: name ?? '', exact: true })).toBeVisible()
  await expect(control).toHaveAttribute('aria-controls', /.+/)
  await control.click()
  await expect(control).toHaveAttribute('aria-expanded', 'false')
  await expect(control).toHaveCount(1)
})

test('e2e_a_long_unbroken_prompt_word_does_not_widen_the_page', async ({ browser, seeded }) => {
  const id = 's-long'
  const begin = Date.now() / 1000 - 60
  const lines = [
    { hook_event_name: 'SessionStart', cwd: seeded.root },
    { _at: 1, hook_event_name: 'UserPromptSubmit', prompt: `see ${'w'.repeat(100)} here` },
    { _at: 2, hook_event_name: 'Stop', last_assistant_message: 'Done' },
  ].map(({ _at, ...event }) =>
    JSON.stringify({ session_id: id, _captured_at: begin + (_at ?? 0), ...event }),
  )
  writeFileSync(join(seeded.home, 'spool', `${id}.jsonl`), `${lines.join('\n')}\n`)
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } })
  const page = await context.newPage()
  await page.goto(`${seeded.url}/sessions/${id}`)
  await page.getByRole('list', { name: 'Entries of turn 1' }).waitFor({ timeout: TIMEOUT })

  const [scroll, client] = await scroller(page).evaluate(
    (m) => [m.scrollWidth, m.clientWidth] as const,
  )
  expect(scroll).toBeLessThanOrEqual(client)
  await context.close()
})
