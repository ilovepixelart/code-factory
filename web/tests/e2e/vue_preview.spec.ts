// A ticket shows preview availability only when its repository configures a command.

import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import type { Page } from '@playwright/test'
import { type Served, TIMEOUT, expect, git, test } from './fixtures'

async function ticket(page: Page, served: Served): Promise<void> {
  await page.goto(`${served.url}/tickets/sample/CF-2`)
  await page.getByRole('form', { name: 'Edit ticket CF-2' }).waitFor({ timeout: TIMEOUT })
}

test('e2e_the_preview_button_shows_only_when_a_preview_command_is_set', async ({
  served,
  writesBoard,
}, testInfo) => {
  const root = testInfo.outputPath('sample')
  const config = join(root, '.code-factory')
  mkdirSync(config, { recursive: true })
  git(root, 'init', '-q', '-b', 'main')
  git(root, 'commit', '-q', '--allow-empty', '-m', 'Initial commit')
  const tracked = await served.api('POST', '/api/repositories', { path: root })
  expect(tracked.status).toBe(201)

  const [status] = await Promise.all([
    writesBoard.waitForResponse((answer) => answer.url().endsWith('/CF-2/preview')),
    ticket(writesBoard, served),
  ])
  expect(status.ok()).toBe(true)
  const preview = writesBoard.getByRole('region', { name: 'Preview' })
  await expect(preview).toHaveCount(0)

  writeFileSync(join(config, 'config.toml'), '[preview]\ncommand = "true"\n')
  await ticket(writesBoard, served)

  await expect(preview).toContainText('This board has no isolated preview runtime.', {
    timeout: TIMEOUT,
  })
  await expect(preview.getByRole('button', { name: 'Preview', exact: true })).toHaveCount(0)
})
