// CF-1203 acceptance flows: the Flow page shows what shipped from git's own history, served by the
// server over the writes sample with a pull request merged into main. CF-1215: and whether
// what shipped held.

import { writeFileSync } from 'node:fs'
import { join } from 'node:path'
import type { Page } from '@playwright/test'
import { Served, TIMEOUT, expect, git, test } from './fixtures'

/** CF-2's branch with one commit, merged into main the way GitHub merges pull request #12. */
function merged(served: Served): void {
  const main = git(served.root, 'rev-parse', '--abbrev-ref', 'HEAD')
  git(served.root, 'checkout', '-q', '-b', 'ticket/cf-2')
  writeFileSync(join(served.root, 'shipped.txt'), 'shipped\n')
  git(served.root, 'add', 'shipped.txt')
  git(served.root, 'commit', '-q', '-m', 'CF-2: ship it')
  git(served.root, 'checkout', '-q', main)
  git(
    served.root,
    'merge',
    '-q',
    '--no-ff',
    '-m',
    'Merge pull request #12 from o/ticket/cf-2',
    'ticket/cf-2',
  )
}

/**
 * The ticket's week (CF-1214) in the board's records, dated now: flint on a local model finished
 * 0 of 14 runs (5 exited 1, 4 stopped at its token cap, 5 after 80 tool calls with no change),
 * the default agent 3 of 4.
 */
function localRuns(served: Served): void {
  const now = Date.now() / 1000
  const run = (agent: string, model: string, exit: number, halted: string, index: number) => ({
    id: `flow-${agent}-${String(index)}`,
    ticket_id: 'CF-2',
    repository: served.root,
    branch: '',
    worktree: served.root,
    stage: 'build',
    pid: 2147483647,
    started_at: now - 3600 - index,
    ended_at: now - 1800,
    log: 'flow.log',
    loop: false,
    exit_code: exit,
    halted,
    agent,
    model,
  })
  const flint = (exit: number, halted: string, count: number, from: number) =>
    Array.from({ length: count }, (_, i) => run('flint', 'qwen3-coder', exit, halted, from + i))
  const runs = [
    ...flint(1, '', 5, 0),
    ...flint(-15, 'stopped at its cap: flint 2,000,113 of 2,000,000 tokens', 4, 5),
    ...flint(-15, 'read enough: stopped at 80 tool calls with no change in its worktree', 5, 9),
    ...[0, 0, 0, 1].map((exit, i) => run('', 'opus', exit, '', 20 + i)),
  ]
  writeFileSync(join(served.home, 'runs.json'), JSON.stringify(runs))
  const agents = [
    {
      name: 'flint',
      runtime: 'claude',
      connection: 'studio',
      model: 'qwen3-coder',
      roles: ['spec', 'build', 'review'],
    },
  ]
  writeFileSync(join(served.home, 'agents.json'), JSON.stringify(agents))
}

/** A branch whose commit says it reverts pull request #12, merged as pull request #13. */
function reverted(served: Served): void {
  git(served.root, 'checkout', '-q', '-b', 'revert/cf-2')
  writeFileSync(join(served.root, 'shipped.txt'), '')
  git(served.root, 'add', 'shipped.txt')
  git(served.root, 'commit', '-q', '-m', 'Revert shipping it\n\nThis reverts #12.')
  git(served.root, 'checkout', '-q', 'main')
  git(
    served.root,
    'merge',
    '-q',
    '--no-ff',
    '-m',
    'Merge pull request #13 from o/revert/cf-2',
    'revert/cf-2',
  )
}

/** How far the page scrolls sideways. */
function sideways(page: Page): Promise<number> {
  return page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
}

test('e2e_flow_shows_a_merged_pull_request_with_its_ticket', async ({ served, writesBoard }) => {
  merged(served)
  await writesBoard.goto(`${served.url}/flow`)
  const recent = writesBoard.getByRole('region', { name: /^Recently merged/ })
  const row = recent.getByRole('row').filter({ hasText: 'CF-2' })
  await row.waitFor({ timeout: TIMEOUT })

  await expect(row).toContainText('#12')
  await expect(row.getByRole('link', { name: /CF-2/ })).toHaveAttribute(
    'href',
    '/tickets/sample/CF-2',
  )
  await expect(
    writesBoard.getByRole('region', { name: 'Shipped' }).getByRole('img'),
  ).toHaveAttribute('aria-label', /: 1$/)
  await expect(
    writesBoard
      .getByRole('region', { name: 'At a glance' })
      .getByLabel('Shipped')
      .getByText('1', { exact: true }),
  ).toBeVisible()
})

// CF-1215: of the two merges, the one a later commit reverted counts under Reverted, and the
// figure's link lists it alone.
test('e2e_flow_lists_a_reverted_merge_behind_its_figure', async ({ served, writesBoard }) => {
  merged(served)
  reverted(served)
  await writesBoard.goto(`${served.url}/flow`)
  const tile = writesBoard.getByRole('region', { name: 'Whether it held' }).getByLabel('Reverted')
  await tile.waitFor({ timeout: TIMEOUT })

  await expect(tile.getByText('1', { exact: true })).toBeVisible()
  await expect(tile).toContainText('50% of 2 merged')
  await tile.getByRole('link', { name: 'show them' }).click()

  await writesBoard.waitForURL('**/flow?held=reverted', { timeout: TIMEOUT })
  const rows = writesBoard.getByRole('region', { name: /^Recently merged/ }).getByRole('row')
  await expect(rows).toHaveCount(2)
  await expect(rows.filter({ hasText: 'CF-2' })).toContainText('reverted')
  await expect(writesBoard.getByRole('heading', { name: /^Recently merged/ })).toBeInViewport()
})

test('e2e_flow_window_is_kept_in_the_address', async ({ served, writesBoard }) => {
  await writesBoard.goto(`${served.url}/flow`)
  const window = writesBoard.getByRole('navigation', { name: 'Range' })
  await window.getByRole('tab', { name: '30 days' }).click()

  await writesBoard.waitForURL('**/flow?range=30d', { timeout: TIMEOUT })
  await expect(window.getByRole('tab', { name: '30 days' })).toHaveAttribute('aria-current', 'page')
  await expect(writesBoard.getByRole('region', { name: 'Shipped' })).toContainText('per day')
})

test.describe('the runs of a fixed sample', () => {
  test.use({ follow: false })

  test('e2e_flow_names_each_agents_model_connection_and_how_its_runs_ended', async ({
    served,
    writesBoard,
  }) => {
    localRuns(served)
    await writesBoard.goto(`${served.url}/flow`)
    const runs = writesBoard.getByRole('region', { name: /^Agent runs/ })
    const flint = runs.getByRole('row').filter({ hasText: 'flint' })
    await flint.waitFor({ timeout: TIMEOUT })

    await expect(flint.getByRole('cell')).toHaveText([
      'flint',
      'qwen3-coder',
      'studio',
      '14',
      '0 0%',
      '5',
      '9',
      '0',
      'exit 1 5, no change after 80 tool calls 5, token cap 4',
      'not reported',
      'not reported',
    ])
    await expect(
      runs.getByRole('row').filter({ hasText: 'the default agent' }).getByRole('cell'),
    ).toHaveText([
      'the default agent',
      'opus',
      'no connection',
      '4',
      '3 75%',
      '1',
      '0',
      '0',
      'exit 1 1',
      'not reported',
      'not reported',
    ])
  })
})

for (const width of [1024, 390]) {
  test(`e2e_flow_fits_${String(width)}`, async ({ served, browser }) => {
    merged(served)
    localRuns(served)
    const context = await browser.newContext({ viewport: { width, height: 800 } })
    const page = await context.newPage()
    await page.goto(`${served.url}/flow`)
    await page.getByRole('heading', { name: 'Recently merged' }).waitFor({ timeout: TIMEOUT })

    expect(await sideways(page)).toBe(0)
    await context.close()
  })
}

// CF-1316: an estimated cost is the amount led by `~`, so at 390 px the Cost column is as wide as
// its amount and the title column keeps the width its cell asks for (14rem).
test('e2e_flow_keeps_the_title_column_wide_beside_an_estimated_cost_at_390', async ({
  served,
  browser,
}) => {
  merged(served)
  const now = Date.now() / 1000
  const run = {
    id: 'flow-est',
    ticket_id: 'CF-2',
    repository: served.root,
    branch: '',
    worktree: served.root,
    stage: 'build',
    pid: 2147483647,
    started_at: now - 600,
    ended_at: now - 60,
    log: 'flow.log',
    loop: false,
    exit_code: 0,
    agent: 'flint',
    cost: 12.5,
    cost_estimated: true,
    tokens: 3000,
  }
  writeFileSync(join(served.home, 'runs.json'), JSON.stringify([run]))
  const context = await browser.newContext({ viewport: { width: 390, height: 800 } })
  const page = await context.newPage()
  await page.goto(`${served.url}/flow`)
  const table = page.getByRole('region', { name: /^Recently merged/ })
  await table.getByRole('cell', { name: '~$12.50' }).waitFor({ timeout: TIMEOUT })

  const width = (name: string) =>
    table.getByRole('columnheader', { name }).evaluate((e) => e.getBoundingClientRect().width)
  expect(await width('Work')).toBeGreaterThanOrEqual(224)
  expect(await width('Cost')).toBeLessThanOrEqual(80)
  expect(await sideways(page)).toBe(0)
  await context.close()
})

// A tick label is never cut and never runs over or touches another (4 px apart at least) at any width: the visible ones read whole.
for (const width of [390, 639, 640, 768, 1024, 1280, 1536]) {
  for (const range of ['24h', '7d', '30d']) {
    test(`e2e_flow_shipped_ticks_do_not_collide_at_${String(width)}_${range}`, async ({
      served,
      browser,
    }) => {
      merged(served)
      const context = await browser.newContext({ viewport: { width, height: 800 } })
      const page = await context.newPage()
      await page.goto(`${served.url}/flow?range=${range}`)
      await page.getByRole('heading', { name: 'Recently merged' }).waitFor({ timeout: TIMEOUT })

      const found = await page
        .getByRole('region', { name: 'Shipped' })
        .getByRole('img')
        .evaluate((chart) => {
          const ticks = [...chart.querySelectorAll('[data-tick]')].filter(
            (t) => getComputedStyle(t).visibility === 'visible',
          )
          const boxes = ticks.map((t) => t.getBoundingClientRect())
          const gaps = boxes.slice(1).map((box, n) => box.left - (boxes[n]?.right ?? box.left))
          return {
            shown: ticks.length,
            cut: ticks.filter((t) => t.scrollWidth > t.clientWidth).length,
            gap: Math.min(...gaps),
          }
        })
      expect(found.shown).toBeGreaterThan(0)
      expect(found.cut).toBe(0)
      expect(found.gap).toBeGreaterThanOrEqual(4)
      await context.close()
    })
  }
}

test('e2e_flow_stat_tile_is_a_named_group', async ({ served, writesBoard }) => {
  merged(served)
  await writesBoard.goto(`${served.url}/flow`)

  await expect(
    writesBoard
      .getByRole('region', { name: 'At a glance' })
      .getByRole('group', { name: 'Shipped' }),
  ).toBeVisible({ timeout: TIMEOUT })
})
