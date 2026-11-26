// CF-671 acceptance: the ticket page's Agent section says how the repository's monthly budget
// stands, served by the server over the writes sample.

import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { expect, test } from './fixtures'

// The run below must stay as written: no follower ends or rewrites it.
test.use({ follow: false })

/** Set `[agents] monthly_budget_usd` in the sample repository's config. */
function setMonthlyBudget(root: string, dollars: number): void {
  const folder = join(root, '.code-factory')
  const path = join(folder, 'config.toml')
  mkdirSync(folder, { recursive: true })
  const text = existsSync(path) ? readFileSync(path, 'utf8') : ''
  const line = `monthly_budget_usd = ${String(dollars)}`
  writeFileSync(
    path,
    text.includes('[agents]')
      ? text.replace('[agents]', `[agents]\n${line}`)
      : `${text}\n[agents]\n${line}\n`,
  )
}

// CF-671-A1 (CF-671-R3, CF-671-R5): a run started the moment the test writes it falls in the
// month the board reads, whatever the day.
test('e2e_the_ticket_page_says_the_month_budget_is_reached', async ({ served, writesBoard }) => {
  setMonthlyBudget(served.root, 2)
  const now = Date.now() / 1000
  const run = {
    id: 'e2e-month',
    ticket_id: 'CF-2',
    repository: served.root,
    branch: '',
    worktree: '',
    stage: 'build',
    pid: 2_147_483_647,
    started_at: now,
    log: '',
    loop: false,
    exit_code: 0,
    ended_at: now,
    cost: 5,
  }
  writeFileSync(join(served.home, 'runs.json'), JSON.stringify([run]))

  await writesBoard.goto(`${served.url}/tickets/sample/CF-2`)

  await expect(writesBoard.getByLabel('Month budget')).toHaveText(
    'Month budget: $5.00 of $2.00, reached',
  )
})
