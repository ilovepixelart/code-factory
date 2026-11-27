// An agent's proposal waits in the Inbox until the owner approves it.

import type { Page } from '@playwright/test'
import { TIMEOUT, expect, present, seedInbox, test, type Served } from './fixtures'

const STATEMENT = 'Measure before tuning'
const WHY = 'A guess cost a day'

async function openProposal(page: Page, served: Served, scope: string) {
  seedInbox(served, {
    ticket: 'CF-2',
    memoryProposal: { statement: STATEMENT, why: WHY, scope },
  })
  const saved = await served.api('GET', '/api/memory')
  expect(saved.status).toBe(200)
  const { unreviewed } = saved.json as { unreviewed: { id: string; statement: string }[] }
  const entry = present(
    unreviewed.find((entry) => entry.statement === STATEMENT),
    'the proposal',
  )
  const path = `/api/memory/sample/${entry.id}`
  await page.goto(`${served.url}/inbox`)
  const section = page.getByRole('region', { name: /^Memory proposals/ })
  const item = section.getByRole('listitem').filter({ hasText: STATEMENT })
  await expect(item).toBeVisible({ timeout: TIMEOUT })
  return { section, item, path }
}

test('e2e_a_memory_proposal_is_approved_from_the_inbox', async ({ served, writesBoard }) => {
  const { section, item, path } = await openProposal(writesBoard, served, '')

  await expect(item.getByText('agent', { exact: true })).toBeVisible()
  await expect(item.getByText(`Why: ${WHY}`)).toBeVisible()
  expect((await served.api('GET', path)).json).toMatchObject({ proposed: true, reviewed: '' })
  await item.getByRole('button', { name: 'Approve' }).click()

  await expect(section).toHaveCount(0, { timeout: TIMEOUT })
  expect((await served.api('GET', path)).json).toMatchObject({
    proposed: false,
    reviewed: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
  })
})

test('e2e_editing_a_scoped_inbox_proposal_can_make_it_load_in_every_session', async ({
  served,
  writesBoard,
}) => {
  const { section, item, path } = await openProposal(writesBoard, served, 'build')
  await item.getByRole('button', { name: 'Edit' }).click()
  const edit = section.getByRole('form', { name: 'Edit the proposal' })
  const scope = edit.getByRole('combobox', { name: 'Loads in' })

  await expect(scope).toHaveValue('build')
  await scope.selectOption({ label: 'Every session' })
  await edit.getByRole('button', { name: 'Save' }).click()

  await expect(edit).toHaveCount(0)
  expect((await served.api('GET', path)).json).toMatchObject({ proposed: true, scope: '' })
  await item.getByRole('button', { name: 'Approve' }).click()
  await expect(section).toHaveCount(0)
  expect((await served.api('GET', path)).json).toMatchObject({ proposed: false, scope: '' })
})
