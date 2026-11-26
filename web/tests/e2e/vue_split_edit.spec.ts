// CF-250: a split's proposed ticket is read and edited in its Inbox item, then accepted.

import { writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { TIMEOUT, expect, test } from './fixtures'

const PROPOSAL = `# Split of CF-2

## 1. Import the brief
type: feature
labels: agents

Read the brief file.

## 2. Show the import
type: bug
blocked_by: 1

Show it on the board.

## Open questions

- Create the tickets above as children of CF-2?
  - [ ] Accept (recommended): creates them as written above
  - [ ] Decline: discards this proposal
`

// CF-250-R7 (CF-250-A1, A2)
test('e2e_a_proposed_ticket_is_edited_from_the_inbox', async ({ served, writesBoard }) => {
  writeFileSync(join(served.root, '.code-factory/tickets/CF-2/split.md'), PROPOSAL)

  await writesBoard.goto(`${served.url}/inbox`)

  const proposed = writesBoard.getByRole('list', { name: 'Proposed tickets' })
  await expect(proposed.getByText('Show the import')).toBeVisible({ timeout: TIMEOUT })
  await expect(proposed.getByText('waits on 1')).toBeVisible()

  await proposed
    .getByRole('listitem')
    .filter({ hasText: 'Show the import' })
    .getByRole('button', { name: 'Edit' })
    .click()
  const form = writesBoard.getByRole('form', { name: 'Edit ticket 2' })
  await form.getByLabel('Title').fill('Draft the requirements')
  await form.getByRole('button', { name: 'Save' }).click()

  await expect(proposed.getByText('Draft the requirements')).toBeVisible({ timeout: TIMEOUT })

  const question = writesBoard.getByRole('listitem').filter({ has: proposed })
  await question.getByRole('button', { name: /Accept/ }).click()

  await expect(proposed).toHaveCount(0, { timeout: TIMEOUT })
})
