// CF-1168 acceptance flow: an agent's memory proposal waits in the Inbox with its source, and
// Approve makes it an entry sessions load, served by the server over the writes sample state.

import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { TIMEOUT, expect, test } from './fixtures'

const PROPOSAL =
  '---\nkind: rule\ndate: 2026-10-01\nsource: agent\nwhy: A guess cost a day\nproposed: true\n---\nMeasure before tuning\n'

// CF-1168-A3
test('e2e_a_memory_proposal_is_approved_from_the_inbox', async ({ served, writesBoard }) => {
  const memory = served.writeMemory({ '2026-10-01-measure-before-tuning.md': PROPOSAL })
  await writesBoard.goto(`${served.url}/inbox`)
  const section = writesBoard.getByRole('region', { name: 'Memory proposals' })
  const item = section.getByRole('listitem').filter({ hasText: 'Measure before tuning' })
  await item.waitFor({ timeout: TIMEOUT })

  await expect(item.getByText('agent', { exact: true })).toBeVisible()
  await expect(item.getByText('Why: A guess cost a day')).toBeVisible()
  await item.getByRole('button', { name: 'Approve' }).click()

  await expect(section).toHaveCount(0, { timeout: TIMEOUT })
  const file = readFileSync(join(memory, '2026-10-01-measure-before-tuning.md'), 'utf8')
  expect(file).not.toContain('proposed')
  expect(file).toMatch(/\nreviewed: \d{4}-\d{2}-\d{2}\n/)
})
