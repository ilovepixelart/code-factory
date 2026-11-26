// CF-1371: the ticket page has a message field on a ticket an agent works only, and a message sent
// from it shows in the ticket's activity, served by the server without the run follower so the
// written run stays as written.

import { writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { TIMEOUT, expect, serve, test as base } from './fixtures'
import type { Served } from './fixtures'

/** A pid no process can hold, so nothing a test writes is ever signalled. */
const NO_PROCESS = 2_147_483_647

const test = base.extend<{ running: Served }>({
  running: async ({}, use) => {
    const { served, stop } = await serve('writes', 'false', false)
    writeFileSync(
      join(served.home, 'runs.json'),
      JSON.stringify([
        {
          id: 'r-msg',
          ticket_id: 'CF-2',
          repository: served.root,
          branch: '',
          worktree: '',
          stage: 'build',
          pid: NO_PROCESS,
          started_at: Date.now() / 1000,
          log: '',
          loop: false,
        },
      ]),
    )
    await use(served)
    stop()
  },
})

test('e2e_a_message_to_the_running_agent_shows_in_the_activity', async ({ running, page }) => {
  await page.goto(`${running.url}/tickets/sample/CF-2`)
  const field = page.getByRole('textbox', { name: 'Message to the running agent' })
  await field.waitFor({ timeout: TIMEOUT })

  await field.fill('Use files, not a database.')
  await page.getByRole('button', { name: 'Send message' }).click()

  const activity = page.getByRole('list', { name: 'Activity' })
  await expect(activity).toContainText('sent a message to the running agent', { timeout: TIMEOUT })
  await expect(activity).toContainText('Use files, not a database.')
  await expect(field).toHaveValue('')
})

test('e2e_a_ticket_no_agent_works_has_no_message_field', async ({ running, page }) => {
  await page.goto(`${running.url}/tickets/sample/CF-1`)
  await page.getByRole('textbox', { name: 'New comment' }).waitFor({ timeout: TIMEOUT })

  await expect(page.getByRole('textbox', { name: 'Message to the running agent' })).toHaveCount(0)
})
