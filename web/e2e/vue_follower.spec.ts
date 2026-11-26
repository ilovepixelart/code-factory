// CF-231 acceptance flow: the checks run from the Vue ticket page, served by the server
// over the writes sample state.

import { writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { TIMEOUT, expect, git, test } from './fixtures'

test('e2e_checks_run_from_the_ticket_page', async ({ served, writesBoard }) => {
  const root = served.root
  writeFileSync(
    join(root, '.code-factory', 'config.toml'),
    '[checks]\ncommand = "true"\n[agents]\nsandbox = false\n',
  )
  git(root, 'branch', 'feat/CF-2')
  const head = git(root, 'rev-parse', 'feat/CF-2')
  served.editTicket('CF-2', 'rank: 2\n', 'rank: 2\nbranch: feat/CF-2\n')
  await writesBoard.goto(`${served.url}/tickets/sample/CF-2`)
  const page = writesBoard.getByRole('main')
  await page.getByText('Checks not run yet.').waitFor({ timeout: TIMEOUT })
  await page.getByRole('button', { name: 'Run checks' }).click()
  const result = page.getByLabel('Checks').getByText('Checks passed on')
  await result.waitFor({ timeout: TIMEOUT })
  const shown = await result.innerText()

  expect(shown.split(/\s+/).filter(Boolean)).toStrictEqual([
    'Checks',
    'passed',
    'on',
    head.slice(0, 7),
  ])
})
