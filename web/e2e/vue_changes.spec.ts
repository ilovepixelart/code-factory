// CF-228 acceptance flows: a ticket branch's changes on the Vue ticket page, served by the
// server over the writes sample state.

import { readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import type { Locator, Page } from '@playwright/test'
import { type Served, TIMEOUT, expect, git, test } from './fixtures'

/** Give CF-2 a branch that edits app.py and adds notes.md. */
function branchWithChanges(served: Served): void {
  const root = served.root
  writeFileSync(join(root, 'app.py'), 'import os\nprint("old")\n')
  git(root, 'add', 'app.py')
  git(root, 'commit', '-q', '-m', 'App')
  git(root, 'checkout', '-q', '-b', 'feat/CF-2')
  writeFileSync(join(root, 'app.py'), 'import os\nprint("new")\n')
  writeFileSync(join(root, 'notes.md'), 'fresh\n')
  git(root, 'add', 'app.py', 'notes.md')
  git(root, 'commit', '-q', '-m', 'Work')
  git(root, 'checkout', '-q', 'main')
  served.editTicket('CF-2', 'rank: 2\n', 'rank: 2\nbranch: feat/CF-2\n')
}

async function changes(page: Page, served: Served, id: string): Promise<Locator> {
  await page.goto(`${served.url}/tickets/sample/${id}`)
  await page.getByRole('form', { name: `Edit ticket ${id}` }).waitFor({ timeout: TIMEOUT })
  return page.getByRole('region', { name: /^Changes/ })
}

test('e2e_the_ticket_page_shows_its_changes', async ({ served, writesBoard }) => {
  branchWithChanges(served)
  const section = await changes(writesBoard, served, 'CF-2')
  await section.getByRole('table', { name: 'app.py' }).waitFor({ timeout: TIMEOUT })
  const heading = await section.getByRole('heading', { level: 2 }).innerText()
  const summary = section.getByText('files, feat/CF-2 against main')
  await expect(summary).toHaveText('files, feat/CF-2 against main')
  const rows = (
    await section.getByRole('table', { name: 'app.py' }).getByRole('row').allInnerTexts()
  ).map((row) => row.split(/\s+/).filter(Boolean).slice(0, 4).join(' '))
  await expect(section.getByRole('heading', { name: 'notes.md', level: 3 })).toHaveCount(1)

  const without = await changes(writesBoard, served, 'CF-1')
  // CF-1 is read, and names no branch: the changes follow that reading.
  const page = writesBoard.getByRole('form', { name: 'Edit ticket CF-1' })
  await expect(page.getByRole('textbox', { name: 'Title' })).toHaveValue('Specs written')
  await expect(page.getByLabel('Branch', { exact: true })).toHaveValue('')

  expect(heading.split(/\s+/).filter(Boolean)).toStrictEqual(['Changes', ',', '2'])
  expect(rows[0]?.startsWith('1 import os')).toBe(true)
  expect(rows[1]?.startsWith('- print("old")')).toBe(true)
  expect(rows[2]?.startsWith('2 + print("new")')).toBe(true)
  await expect(without).toHaveCount(0)
})

test('e2e_a_line_comment_is_recorded', async ({ served, writesBoard }) => {
  branchWithChanges(served)
  const section = await changes(writesBoard, served, 'CF-2')
  const opener = section.getByRole('button', { name: 'Comment on app.py line 2', exact: true })
  await opener.click()
  const text = section.getByRole('textbox', { name: 'Comment on app.py line 2', exact: true })
  await text.fill('Looks off')
  await section.getByRole('button', { name: 'Send comment on app.py line 2' }).click()
  await writesBoard
    .getByRole('form', { name: 'Edit ticket CF-2' })
    .getByText('You commented')
    .waitFor({ timeout: TIMEOUT })
  const activity = join(served.root, '.code-factory', 'tickets', 'CF-2', 'activity.jsonl')
  await expect.poll(() => readFileSync(activity, 'utf8')).toContain('app.py:2: Looks off')

  await expect(text).toHaveValue('')
  await expect(opener).toHaveAttribute('aria-expanded', 'false')
})
