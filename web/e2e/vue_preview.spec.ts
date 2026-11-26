// CF-1379: a ticket's page shows a Preview button only while the repository's `[preview] command`
// is set, served by the server over the writes sample state.

import { appendFileSync } from 'node:fs'
import { join } from 'node:path'
import type { Page } from '@playwright/test'
import { type Served, TIMEOUT, expect, test } from './fixtures'

async function ticket(page: Page, served: Served): Promise<void> {
  await page.goto(`${served.url}/tickets/sample/CF-2`)
  await page.getByRole('form', { name: 'Edit ticket CF-2' }).waitFor({ timeout: TIMEOUT })
}

test('e2e_the_preview_button_shows_only_when_a_preview_command_is_set', async ({
  served,
  writesBoard,
}) => {
  // The flag is read once the page is up: the absence is measured after that answer.
  await Promise.all([
    writesBoard.waitForResponse((answer) => answer.url().endsWith('/CF-2/preview')),
    ticket(writesBoard, served),
  ])
  const button = writesBoard.getByRole('button', { name: 'Preview', exact: true })
  await expect(button).toHaveCount(0)

  appendFileSync(
    join(served.root, '.code-factory', 'config.toml'),
    '\n[preview]\ncommand = "true"\n',
  )
  await ticket(writesBoard, served)

  await expect(button).toHaveCount(1, { timeout: TIMEOUT })
  await expect(writesBoard.getByRole('region', { name: 'Preview' })).toHaveCount(1)
})
