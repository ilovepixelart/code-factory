// CF-1036: the ticket's Agent section shows a running run's progress from its own log.

import { writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { TIMEOUT, expect, serve, test } from './fixtures'

/** Above any real pid: no signal can reach a process, and no follower runs here. */
const NO_PROCESS = 2_147_483_647

// Recorded shape of a pi run, with stand-in names: 3 calls, 2 read and 1 edit; 100 + 5 tokens.
const PI_LOG = `${[
  { type: 'session', version: 3, id: 's', cwd: '/stand-in' },
  {
    type: 'message_end',
    message: {
      role: 'assistant',
      content: [
        { type: 'toolCall', id: 'c1', name: 'read', arguments: {} },
        { type: 'toolCall', id: 'c2', name: 'read', arguments: {} },
        { type: 'toolCall', id: 'c3', name: 'edit', arguments: {} },
      ],
      usage: { input: 100, output: 5 },
    },
  },
]
  .map((record) => JSON.stringify(record))
  .join('\n')}\n`

test('e2e_a_running_run_shows_its_progress', async ({ page }) => {
  const { served, stop } = await serve('writes', 'false', false)
  const log = join(served.home, 'r1.log')
  writeFileSync(log, PI_LOG)
  writeFileSync(
    join(served.home, 'runs.json'),
    JSON.stringify([
      {
        id: 'r1',
        ticket_id: 'CF-2',
        repository: served.root,
        branch: '',
        worktree: served.root,
        stage: 'build',
        pid: NO_PROCESS,
        started_at: Date.now() / 1000,
        log,
        loop: false,
      },
    ]),
  )
  try {
    await page.goto(`${served.url}/tickets/sample/CF-2`)
    const progress = page.getByLabel('Run progress')
    await expect(progress).toContainText('3 tool calls: 2 read, 1 changed file, 0 other', {
      timeout: TIMEOUT,
    })
    await expect(progress).toContainText('105 tokens so far')
    await expect(progress).toContainText('last activity')
    writeFileSync(log, PI_LOG + PI_LOG)
    await expect(progress).toContainText('6 tool calls: 4 read, 2 changed files, 0 other', {
      timeout: TIMEOUT,
    })
  } finally {
    stop()
  }
})
