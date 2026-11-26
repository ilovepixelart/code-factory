// CF-1216 acceptance: a cost the board estimated from a run's tokens is marked as an estimate
// where it shows, served by the server over the writes sample.

import { writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { expect, test } from './fixtures'

// The runs below must stay as written: no follower ends or rewrites them.
test.use({ follow: false })

test('e2e_an_estimated_cost_is_marked_on_flow_the_card_and_the_ticket', async ({
  served,
  writesBoard,
}) => {
  const now = Date.now() / 1000
  const run = (id: string, ticket: string, agent: string, more: object) => ({
    id,
    ticket_id: ticket,
    repository: served.root,
    branch: '',
    worktree: '',
    stage: 'build',
    pid: 2_147_483_647,
    started_at: now - 600,
    log: '',
    loop: false,
    exit_code: 0,
    ended_at: now - 60,
    agent,
    ...more,
  })
  const runs = [
    run('e2e-reported', 'CF-2', '', { cost: 1.2, tokens: 52_000 }),
    run('e2e-hosted', 'CF-2', 'flint', { cost: 2.05, cost_estimated: true, tokens: 3_000_233 }),
    run('e2e-local', 'CF-1', 'qwen-local', { cost: 0, cost_estimated: true, tokens: 812_000 }),
  ]
  writeFileSync(join(served.home, 'runs.json'), JSON.stringify(runs))

  await writesBoard.goto(`${served.url}/flow`)
  const table = writesBoard.getByRole('region', { name: 'Agent runs' })
  await expect(table.getByRole('row')).toHaveCount(4)
  const costs = await table.getByRole('cell', { name: /^~?\$/ }).allInnerTexts()

  await writesBoard.goto(`${served.url}/tickets`)
  const chip = writesBoard.getByText('~$3.25', { exact: true })
  await expect(chip).toBeVisible()
  const title = await chip.getAttribute('title')

  await writesBoard.goto(`${served.url}/tickets/sample/CF-2`)
  const spend = writesBoard.getByRole('heading', { name: /^Agent/ }).getByText('~$3.25')

  expect(costs).toStrictEqual(['~$2.05', '~$0.00', '$1.20'])
  expect(title).toContain("estimated from the runs' tokens")
  await expect(spend).toBeVisible()
})
