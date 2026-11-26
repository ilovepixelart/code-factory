// CF-1162 acceptance flows: the Team page groups what needs the owner, what waits, who works and
// what merged today, served by the server over the writes sample without the run follower,
// so the tickets, runs, jobs, pull requests and activity the tests write stay as written.

import { type ChildProcess, execFileSync, spawn } from 'node:child_process'
import { mkdirSync, realpathSync, rmSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import type { Locator, Page } from '@playwright/test'
import { BINARY, Served, TIMEOUT, expect, git, serve, test as base, useTheme } from './fixtures'

/** A pid no process can hold, so nothing a test writes is ever signalled. */
const NO_PROCESS = 2_147_483_647
const MINUTE = 60
const HOUR = 3600
const DAY = 86_400

const test = base.extend<{ served: Served; child: () => ChildProcess }>({
  served: async ({}, use) => {
    const { served, stop } = await serve('writes', 'false', false)
    write(served, 'runs.json', [])
    await use(served)
    stop()
  },
  // A process of the test's own, ended after it, for a run or a job that still runs.
  child: async ({}, use) => {
    const started: ChildProcess[] = []
    await use(() => {
      const sleeper = spawn('sleep', ['600'], { stdio: 'ignore' })
      started.push(sleeper)
      return sleeper
    })
    for (const sleeper of started) sleeper.kill()
  },
})

const seconds = (): number => Date.now() / 1000
const stamp = (at: number): string => new Date(at * 1000).toISOString().replace(/\.\d{3}Z$/, 'Z')
/** 00:00 UTC of today, where the board's day starts. */
const today = (): number => Math.floor(seconds() / DAY) * DAY

function write(served: Served, file: string, value: unknown): void {
  writeFileSync(join(served.home, file), JSON.stringify(value))
}

/** A ticket of the sample repository, declared in `stage` when one is given. */
function ticket(served: Served, id: string, title: string, stage = ''): void {
  const folder = join(served.root, '.code-factory', 'tickets', id)
  mkdirSync(folder, { recursive: true })
  const declared = stage ? `stage: ${stage}\n` : ''
  writeFileSync(join(folder, 'ticket.md'), `---\nid: ${id}\ntitle: ${title}\n${declared}---\n`)
}

/** Ticket `id`'s activity, each record `[at, kind, data]`. */
function activity(served: Served, id: string, records: [number, string, object][]): void {
  const lines = records.map(([at, kind, data]) => JSON.stringify({ at: stamp(at), kind, ...data }))
  writeFileSync(
    join(served.root, '.code-factory', 'tickets', id, 'activity.jsonl'),
    lines.join('\n') + '\n',
  )
}

/** Open pull requests, by ticket id, as the board last read them. */
function pulls(served: Served, open: Record<string, number>): void {
  const root = realpathSync(served.root)
  write(
    served,
    'pull_requests.json',
    Object.fromEntries(
      Object.entries(open).map(([id, number]) => [
        `${root}/${id}`,
        {
          state: 'open',
          review: '',
          ci: 'none',
          head: 'abc',
          url: `https://example.test/pull/${String(number)}`,
          at: String(seconds()),
        },
      ]),
    ),
  )
}

/** A run of `runs.json` on ticket `id`, its process `pid`. */
function run(served: Served, id: string, agent: string, pid: number, started: number) {
  return {
    id: `run-${id}`,
    ticket_id: id,
    repository: served.root,
    branch: '',
    worktree: '',
    stage: 'build',
    pid,
    started_at: started,
    log: '',
    loop: false,
    exit_code: null,
    ended_at: null,
    agent,
  }
}

/** A land job recorded running on `id`, its process `pid`. */
function landJob(served: Served, id: string, pid: number, started: number): void {
  const folder = join(served.home, 'jobs')
  mkdirSync(folder, { recursive: true })
  const job = `job-${id.toLowerCase().replace(/[^0-9a-f]/g, '')}1`
  writeFileSync(
    join(folder, `${job}.json`),
    JSON.stringify({
      id: job,
      kind: 'land',
      ticket: id,
      state: 'running',
      pid,
      started,
      ended: null,
      exit_code: null,
      log: join(folder, `${job}.log`),
    }),
  )
}

/** Capture a session subagent's hook event, as the hooks would. */
function capture(served: Served, event: object): void {
  execFileSync(BINARY, ['capture'], {
    input: JSON.stringify({ session_id: 's-team', cwd: served.root, ...event }),
    env: { ...process.env, CODE_FACTORY_HOME: served.home },
  })
}

/** A subagent of type `type` editing a file in ticket `id`'s worktree. */
function subagent(served: Served, agent: string, type: string, id: string): void {
  capture(served, { hook_event_name: 'SessionStart' })
  capture(served, { hook_event_name: 'SubagentStart', agent_id: agent, agent_type: type })
  capture(served, {
    hook_event_name: 'PreToolUse',
    agent_id: agent,
    agent_type: type,
    tool_name: 'Edit',
    tool_use_id: `t-${agent}`,
    tool_input: { file_path: `${served.root}/.code-factory/worktrees/${id}/src/a.rs` },
  })
}

function group(page: Page, title: string): Locator {
  return page.getByRole('region', { name: new RegExp(`^${title}`) })
}

function rows(page: Page, title: string): Locator {
  return group(page, title).getByRole('listitem')
}

/** CF-1's open question and its spec waiting for approval (the sample's), CF-70 in Review with #20 open, a subagent on CF-3 and CF-80
 *  merged today. */
function oneOfEach(served: Served): void {
  ticket(served, 'CF-70', 'Waits for review', 'review')
  activity(served, 'CF-70', [
    [seconds() - 30 * MINUTE, 'pull_request', { url: 'https://example.test/pull/20' }],
  ])
  pulls(served, { 'CF-70': 20 })
  subagent(served, 'a1b2c3d4', 'ticket-worker', 'CF-3')
  ticket(served, 'CF-80', 'Landed today', 'merged')
  activity(served, 'CF-80', [
    [today() - HOUR, 'created', { type: 'bug' }],
    [today() + 1, 'stage', { to: 'merged' }],
  ])
}

// CF-1162-R1, CF-1162-R6
test('team_groups_in_attention_order', async ({ served, page }) => {
  oneOfEach(served)

  await page.goto(`${served.url}/team`)

  const headings = page.getByRole('main').getByRole('heading', { level: 2 })
  await expect(headings).toHaveText(
    [
      'Today against this cycle',
      'Needs you, 1',
      'Waiting, 1',
      'Working, 1',
      'Done today, 1',
      'Stale, 0',
    ],
    { timeout: TIMEOUT },
  )
  await expect(page.getByRole('navigation', { name: 'Groups' })).toHaveText(
    /1\s*need you\s*1\s*waiting\s*1\s*working\s*1\s*done today\s*0\s*stale/,
  )
  await expect(page).toHaveTitle('(1) Team · code-factory')

  for (const id of ['CF-1', 'CF-70', 'CF-80']) {
    rmSync(join(served.root, '.code-factory', 'tickets', id), { recursive: true })
  }
  capture(served, {
    hook_event_name: 'SubagentStop',
    agent_id: 'a1b2c3d4',
    agent_type: 'ticket-worker',
  })

  await expect(page.getByText('Nobody is working and nothing waits.')).toBeVisible({
    timeout: TIMEOUT,
  })
  await expect(headings).toHaveText([
    'Today against this cycle',
    'Needs you, 0',
    'Waiting, 0',
    'Working, 0',
    'Done today, 0',
    'Stale, 0',
  ])
  for (const empty of [
    'Nothing needs you',
    'Nothing waits',
    'Nobody is working',
    'Nothing merged today',
    'Nothing is stale',
  ]) {
    await expect(page.getByText(empty, { exact: true })).toBeVisible()
  }
  await expect(page).toHaveTitle('Team · code-factory')
})

// CF-1209: while no ticket reached a stage today or this cycle the strip is one line, not four
// tiles; with one it is the tiles.
test('team_strip_is_one_line_with_nothing_to_show', async ({ served, page }) => {
  await page.goto(`${served.url}/team`)

  const strip = page.getByRole('region', { name: 'Today against this cycle' })
  await expect(strip.getByText('No ticket reached a stage today or this cycle.')).toBeVisible({
    timeout: TIMEOUT,
  })
  await expect(strip.getByRole('list', { name: 'Stage times' })).toHaveCount(0)

  ticket(served, 'CF-80', 'Landed today', 'merged')
  activity(served, 'CF-80', [
    [today() - HOUR, 'created', { type: 'bug' }],
    [today() + 1, 'stage', { to: 'merged' }],
  ])

  await expect(strip.getByRole('list', { name: 'Stage times' }).getByRole('listitem')).toHaveCount(
    4,
    { timeout: TIMEOUT },
  )
  await expect(strip.getByText('No ticket reached a stage today or this cycle.')).toHaveCount(0)
})

// CF-1209: a ticket the owner must answer whose land job also died is one row, in Needs you, the
// dead job its second line; Stale holds no row of it.
test('team_ticket_in_two_states_is_one_row', async ({ served, page }) => {
  landJob(served, 'CF-1', NO_PROCESS, seconds() - 20 * MINUTE)

  await page.goto(`${served.url}/team`)

  await expect(rows(page, 'Needs you')).toHaveText(
    [
      /^Waiting on you\s*CF-1\s*.*you\s*1 open question\s*also stale 20m: board land, landing; its process has ended\s*\d+s$/,
    ],
    { timeout: TIMEOUT },
  )
  await expect(rows(page, 'Stale')).toHaveCount(0)
  await expect(page.getByRole('navigation', { name: 'Groups' })).toHaveText(
    /1\s*need you\s*0\s*waiting\s*0\s*working\s*0\s*done today\s*0\s*stale/,
  )
})

// CF-1209, CF-1197: a group holds 10 rows a page under its own prefix, the next page a link.
test('team_group_pages_ten_rows', async ({ served, page }) => {
  const now = seconds()
  const open: Record<string, number> = {}
  for (let n = 1; n <= 12; n += 1) {
    const id = `CF-${String(100 + n)}`
    ticket(served, id, `Review ${String(n)}`, 'review')
    activity(served, id, [
      [now - (60 - n) * MINUTE, 'pull_request', { url: `https://example.test/pull/${String(n)}` }],
    ])
    open[id] = n
  }
  pulls(served, open)

  await page.goto(`${served.url}/team`)

  const waiting = group(page, 'Waiting')
  await expect(waiting.getByRole('heading', { level: 2 })).toHaveText('Waiting, 12', {
    timeout: TIMEOUT,
  })
  await expect(rows(page, 'Waiting').getByRole('link', { name: /^CF-/ })).toHaveText(
    ['101', '102', '103', '104', '105', '106', '107', '108', '109', '110'].map((n) => `CF-${n}`),
  )
  const pages = waiting.getByRole('navigation', { name: 'Pages of waiting' })
  await expect(pages.getByTestId('page-range')).toHaveText('1 to 10 of 12')
  await expect(page.getByRole('navigation', { name: 'Pages of needs you' })).toHaveCount(0)

  await pages.getByRole('link', { name: 'Next ›' }).click()

  await expect(page).toHaveURL(/\/team\?waiting_page=2$/)
  await expect(rows(page, 'Waiting').getByRole('link', { name: /^CF-/ })).toHaveText([
    'CF-111',
    'CF-112',
  ])
  await expect(pages.getByTestId('page-range')).toHaveText('11 to 12 of 12')
})

// CF-1162-R2, CF-1162-R3, CF-1233
test('team_lists_every_kind_of_worker', async ({ served, page, child }) => {
  const builder = child()
  const lander = child()
  const now = seconds()
  write(served, 'agents.json', [
    { name: 'builder', runtime: 'claude', roles: ['build'] },
    { name: 'writer', runtime: 'claude', roles: ['spec'] },
    { name: 'muse', runtime: 'claude', roles: ['spec'], paused_at: Math.floor(now) - 60 },
  ])
  write(served, 'runs.json', [run(served, 'CF-3', 'builder', builder.pid ?? NO_PROCESS, now - 40)])
  subagent(served, 'e41d0000', 'ticket-worker', 'CF-2')
  // On a ticket of its own: CF-1's open question would take its row to Needs you (CF-1209).
  ticket(served, 'CF-60', 'Lands')
  landJob(served, 'CF-60', lander.pid ?? NO_PROCESS, now - 20)

  await page.goto(`${served.url}/team`)

  const working = rows(page, 'Working')
  await expect(working).toHaveText(
    [
      /^Working\s*CF-3\s*Declared\s*builder\s*build run\s*\d+s$/,
      /^Working\s*CF-60\s*Lands\s*board land\s*landing\s*\d+s$/,
      new RegExp(
        `^Working\\s*CF-2\\s*.*ticket-worker e41d\\s*Edit ${served.root}/\\.code-factory/worktrees/CF-2/src/a\\.rs\\s*\\d+s$`,
      ),
    ],
    { timeout: TIMEOUT },
  )
  await expect(working.getByRole('link', { name: 'CF-3' })).toHaveAttribute(
    'href',
    '/tickets/sample/CF-3',
  )
  await expect(group(page, 'Working')).toContainText('Idle: writer')
  await expect(group(page, 'Working')).not.toContainText('Idle: writer, muse')
  await expect(group(page, 'Working')).toContainText('Paused: muse')
})

// CF-1162-R4, CF-1162-R9
test('team_typed_waits_oldest_first', async ({ served, page }) => {
  const now = seconds()
  ticket(served, 'CF-70', 'Waits for review', 'review')
  activity(served, 'CF-70', [
    [now - 30 * MINUTE, 'pull_request', { url: 'https://example.test/pull/20' }],
  ])
  ticket(served, 'CF-80', 'Conflicts', 'review')
  activity(served, 'CF-80', [
    [now - 50 * MINUTE, 'pull_request', { url: 'https://example.test/pull/21' }],
    [now - 9 * MINUTE, 'branch_conflict', { default: 'abc' }],
  ])
  pulls(served, { 'CF-70': 20, 'CF-80': 21 })

  await page.goto(`${served.url}/team`)

  const waiting = rows(page, 'Waiting')
  await expect(waiting).toHaveText(
    [
      /^Waiting\s*CF-70\s*Waits for review\s*reviewer\s*waiting for review pickup since #20 opened\s*#20\s*checks not run\s*30m$/,
      /^Waiting\s*CF-80\s*Conflicts\s*build agent\s*conflicts with main\s*#21\s*conflict\s*9m$/,
    ],
    { timeout: TIMEOUT },
  )
  await expect(waiting.getByRole('link', { name: '#20' })).toHaveAttribute(
    'href',
    'https://example.test/pull/20',
  )
})

// CF-1162-R5, CF-1193-R4: the owner's decisions need the owner; stale work sits in its own group,
// below every live one.
test('team_stale_rows_sit_below_live_work', async ({ served, page }) => {
  const now = seconds()
  write(served, 'runs.json', [run(served, 'CF-3', 'builder', NO_PROCESS, now - 30 * MINUTE)])
  // A stale row older than an hour has ended and leaves the page (CF-1193).
  landJob(served, 'CF-2', NO_PROCESS, now - 45 * MINUTE)

  await page.goto(`${served.url}/team`)

  await expect(rows(page, 'Needs you')).toHaveText(
    [/^Waiting on you\s*CF-1\s*.*you\s*1 open question\s*\d+s$/],
    { timeout: TIMEOUT },
  )
  await expect(rows(page, 'Stale')).toHaveText([
    /^Stale\s*CF-2\s*.*board land\s*landing; its process has ended\s*45m$/,
    /^Stale\s*CF-3\s*Declared\s*builder\s*build run; its process has ended\s*30m$/,
  ])
  await expect(rows(page, 'Working')).toHaveCount(0)
  const headings = await page.getByRole('main').getByRole('heading', { level: 2 }).allTextContents()
  expect(headings.at(-1)).toBe('Stale, 2')
})

// CF-1162-R7
test('team_stage_times_today_against_cycle', async ({ served, page }) => {
  const merged = (id: string, filed: number, at: number) => {
    ticket(served, id, `Merged ${id}`, 'merged')
    activity(served, id, [
      [filed, 'created', { type: 'feature' }],
      [at, 'stage', { to: 'merged' }],
    ])
  }
  merged('CF-80', today() - HOUR, today() + 60)
  merged('CF-90', today() - 3 * HOUR, today() + 120)
  merged('CF-100', seconds() - 3 * DAY - 2 * HOUR, seconds() - 3 * DAY)

  await page.goto(`${served.url}/team`)

  const strip = page.getByRole('list', { name: 'Stage times' }).getByRole('listitem')
  // Nearest-rank medians: 1h of 1h and 3h today, 2h of 1h, 2h and 3h this cycle.
  await expect(strip).toHaveText(
    [
      /^Filed to first commit/,
      /^to pull request\s*none today\s*no cycle median\s*0 today, 0 this cycle$/,
      /^to checks pass\s*none today\s*no cycle median\s*0 today, 0 this cycle$/,
      /^to merge\s*1h\s*cycle 2h, 59m under\s*2 today, 3 this cycle$/,
    ],
    { timeout: TIMEOUT },
  )
})

// CF-1162-R8
test('team_peek_shows_timeline_and_events', async ({ served, page }) => {
  const now = seconds()
  ticket(served, 'CF-70', 'Waits for review', 'review')
  activity(served, 'CF-70', [
    [now - 2 * HOUR, 'created', { type: 'bug' }],
    [now - 30 * MINUTE, 'pull_request', { url: 'https://example.test/pull/20' }],
  ])
  pulls(served, { 'CF-70': 20 })
  git(served.root, 'commit', '--allow-empty', '-m', 'CF-70: requirements')

  await page.goto(`${served.url}/team`)
  const pick = rows(page, 'Waiting').getByRole('button', { name: 'Waits for review' })
  await pick.click({ timeout: TIMEOUT })

  const peek = page.getByRole('complementary', { name: 'Waits for review' })
  const miles = peek.getByRole('list', { name: 'Stage times from filing' }).getByRole('listitem')
  await expect(miles).toHaveText([
    /^Filed\s*\d\d:\d\d · 0s/,
    /^First commit\s*\d\d:\d\d · 2h/,
    /^Pull request\s*\d\d:\d\d · 1.5h\s*cycle 1.5h/,
    /^Checks pass\s*not yet · 2h so far/,
    /^Merged\s*not yet · 2h so far/,
  ])
  await expect(peek.getByRole('list', { name: 'Last events' }).getByRole('listitem')).toHaveText([
    /Pull request opened \(https:\/\/example\.test\/pull\/20\)/,
    /Created/,
  ])
  // The next read keeps the row selected.
  await page.waitForResponse((r) => r.url().endsWith('/api/team/now'))
  await expect(pick).toHaveAttribute('aria-pressed', 'true')
  await expect(peek).toBeVisible()

  await page.keyboard.press('Escape')

  await expect(peek).toHaveCount(0)
  await expect(pick).toHaveAttribute('aria-pressed', 'false')
})

// CF-1162-R10
test('team_page_design_rules', async ({ served, page }) => {
  oneOfEach(served)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(`${served.url}/team`)
  await expect(rows(page, 'Done today')).toHaveCount(1, { timeout: TIMEOUT })

  for (const theme of ['light', 'dark']) {
    await useTheme(page, theme)
    const sideways = await page.evaluate(() => {
      const main = document.querySelector('[data-scroller]')
      return [
        document.documentElement.scrollWidth - document.documentElement.clientWidth,
        main ? main.scrollWidth - main.clientWidth : 0,
      ]
    })
    expect(sideways, theme).toStrictEqual([0, 0])
  }
  // An error is the destructive Badge and a warning the default one (docs/design.md, Theme).
  const coloured = (title: string) =>
    rows(page, title).evaluateAll((items) =>
      items.map((item) =>
        Boolean(
          item.querySelector(
            '[data-slot="badge"][data-variant="destructive"], [data-slot="badge"]:not([data-variant])',
          ),
        ),
      ),
    )
  expect(await coloured('Needs you')).toStrictEqual([true])
  for (const quiet of ['Waiting', 'Working', 'Done today']) {
    expect(await coloured(quiet), quiet).toStrictEqual([false])
  }
  const inline = await page.evaluate(() => ({
    handlers: [...document.querySelectorAll('*')].filter((e) =>
      [...e.attributes].some((a) => a.name.startsWith('on')),
    ).length,
    scripts: [...document.querySelectorAll('script:not([src])')].length,
    styles: [...document.querySelectorAll('body style')].length,
  }))
  expect(inline).toStrictEqual({ handlers: 0, scripts: 0, styles: 0 })
})

// CF-1162-R11
test('team_shows_read_failure', async ({ served, page }) => {
  oneOfEach(served)
  await page.goto(`${served.url}/team`)
  await expect(rows(page, 'Waiting')).toHaveCount(1, { timeout: TIMEOUT })

  await page.route('**/api/team/now', (route) =>
    route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ error: 'the ledger cannot be read' }),
    }),
  )

  const alert = page.getByRole('alert')
  await expect(alert).toContainText('The Team page could not be read: the ledger cannot be read', {
    timeout: TIMEOUT,
  })
  await expect(alert).toContainText(/Showing the last read, at \d\d:\d\d:\d\d\./)
  await expect(rows(page, 'Waiting')).toHaveCount(1)
})
