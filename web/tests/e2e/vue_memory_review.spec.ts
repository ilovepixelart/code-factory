// Review the Memory page of the app with dated entries backed by PostgreSQL.

import type { Page } from '@playwright/test'
import { TIMEOUT, expect, present, seedMemory, test, toasts } from './fixtures'

const SMALL = {
  day: '2020-01-01',
  kind: 'rule',
  statement: 'Keep every rule small',
  source: 'conversation',
  why: 'Small rules are read',
} as const
const TWICE = {
  day: '2020-01-02',
  kind: 'lesson',
  statement: 'Run the gate once',
  source: 'CF-2',
  why: 'It cost a run',
} as const
const TODAY = new Date().toISOString().slice(0, 10)

const entryPath = (id: string | undefined): string =>
  `/api/memory/sample/${present(id, 'the seeded entry')}`
const reviewDue = (page: Page) => page.getByRole('region', { name: /^Review due\b/ })
const core = (page: Page) => page.getByRole('region', { name: /^Core\b/ })
const history = (page: Page) => page.getByRole('region', { name: /^History\b/ })

test('e2e_memory_entries_are_reviewed_on_the_page', async ({ served, writesBoard }) => {
  const [smallId, twiceId] = seedMemory(served, [SMALL, TWICE])
  await writesBoard.goto(`${served.url}/memory`)
  const due = reviewDue(writesBoard)
  const small = due.getByRole('article', { name: SMALL.statement })
  await small.getByRole('button', { name: 'Still holds' }).click()
  await expect(small).toHaveCount(0)

  const twice = due.getByRole('article', { name: TWICE.statement })
  await twice.getByRole('button', { name: 'Retire' }).click()
  const retire = twice.getByRole('form', { name: 'Retire the entry' })
  await retire
    .getByRole('textbox', { name: 'Why it no longer applies' })
    .fill('The gate refuses it')
  await retire.getByRole('button', { name: 'Retire' }).click()

  const retired = history(writesBoard)
  await expect(retired.getByRole('heading')).toHaveAccessibleName(/^History\s*,\s*1$/)
  await retired.getByRole('button', { name: 'Show' }).click()
  await expect(retired.getByRole('listitem', { name: TWICE.statement })).toContainText(
    'The gate refuses it',
  )
  await expect(due).toHaveCount(0)
  expect((await served.api('GET', entryPath(smallId))).json).toMatchObject({ reviewed: TODAY })
  const page = await served.api('GET', '/api/memory')
  expect(page.json).toMatchObject({
    retired: [{ id: twiceId, retired: 'The gate refuses it' }],
  })
})

test('e2e_a_memory_entry_is_added_from_the_page', async ({ served, writesBoard }) => {
  seedMemory(served, [{ ...SMALL, day: TODAY }])
  await writesBoard.goto(`${served.url}/memory`)
  const meter = writesBoard.getByRole('meter', { name: 'Loaded into every agent session' })
  await expect(core(writesBoard).getByRole('listitem', { name: SMALL.statement })).toBeVisible()
  const before = Number(await meter.getAttribute('value'))
  await writesBoard.getByRole('button', { name: 'Add an entry' }).click()
  const form = writesBoard.getByRole('form', { name: 'Add an entry' })
  await form.getByRole('group', { name: 'Kind' }).getByRole('button', { name: 'Decision' }).click()
  await form.getByRole('textbox', { name: 'Statement' }).fill('Ship one ticket at a time')
  await form.getByRole('textbox', { name: 'Why' }).fill('Parallel tickets collided')
  await expect(form.getByText('Required: where the entry comes from')).toBeVisible()
  await expect(form.getByRole('button', { name: 'Add' })).toBeDisabled()
  await form.getByRole('textbox', { name: 'Source' }).fill('CF-271')
  const stored = writesBoard.waitForResponse(
    (response) => response.url().endsWith('/api/memory') && response.request().method() === 'POST',
  )
  await form.getByRole('button', { name: 'Add' }).click()
  expect((await stored).status()).toBe(201)

  const added = core(writesBoard).getByRole('listitem', { name: 'Ship one ticket at a time' })
  await added.getByText('Ship one ticket at a time').click()
  await expect(added.getByText('Why: Parallel tickets collided')).toBeVisible()
  await expect.poll(async () => Number(await meter.getAttribute('value'))).toBeGreaterThan(before)
  await expect(meter).toHaveAttribute('max', '8000')
})

const EARLIER = 'Run the gate before every push of a ticket branch'
const LATER = 'Run the gate before each push of the ticket branch'

test('e2e_the_memory_page_lists_and_applies_a_proposal', async ({ served, writesBoard }) => {
  const [earlier, later] = seedMemory(served, [
    { ...SMALL, day: '2026-10-01', statement: EARLIER },
    { ...SMALL, day: '2026-10-05', statement: LATER },
  ])
  await writesBoard.goto(`${served.url}/memory`)
  const section = writesBoard.getByRole('region', { name: /^Proposed by consolidate\b/ })
  await expect(section.getByText(`Merge "${LATER}" into "${EARLIER}"`)).toBeVisible({
    timeout: TIMEOUT,
  })
  await section.getByRole('button', { name: 'Apply' }).click()

  await expect(section).toHaveCount(0)
  const page = await served.api('GET', '/api/memory')
  expect(page.json).toMatchObject({ retired: [{ id: later, merged_into: earlier }] })
  await toasts(writesBoard).getByRole('button', { name: 'Undo' }).click()
  await expect(section.getByText(`Merge "${LATER}" into "${EARLIER}"`)).toBeVisible()
  await expect(core(writesBoard).getByRole('listitem', { name: LATER })).toBeVisible()
})

test('e2e_a_flagged_pair_can_be_resolved_and_restored', async ({ served, writesBoard }) => {
  const older = 'Squash ticket branches before landing them through the merge queue'
  const newer = 'Never let the merge queue take ticket branches unsquashed'
  seedMemory(served, [
    { ...SMALL, day: '2026-10-01', statement: older },
    { ...SMALL, day: '2026-10-05', statement: newer },
  ])
  await writesBoard.goto(`${served.url}/memory`)
  const flagged = writesBoard.getByRole('region', { name: /^Flagged by consolidate/ })
  await expect(flagged.getByText('Contradicts', { exact: true })).toBeVisible()
  await expect(flagged).toContainText(older)
  await expect(flagged).toContainText(newer)

  await flagged.getByRole('button', { name: 'Newer supersedes older' }).click()

  await expect(flagged).toHaveCount(0)
  await history(writesBoard).getByRole('button', { name: 'Show' }).click()
  await expect(history(writesBoard).getByRole('listitem', { name: older })).toBeVisible()
  await expect(core(writesBoard).getByRole('listitem', { name: newer })).toBeVisible()
  await toasts(writesBoard).getByRole('button', { name: 'Undo' }).click()
  await expect(flagged.getByText('Contradicts', { exact: true })).toBeVisible()
  await expect(core(writesBoard).getByRole('listitem', { name: older })).toBeVisible()
})

test('e2e_review_due_comes_first_and_empties_when_reviewed', async ({ served, writesBoard }) => {
  const [, staleId] = seedMemory(served, [{ ...SMALL, day: TODAY }, TWICE])
  await writesBoard.goto(`${served.url}/memory`)
  const due = reviewDue(writesBoard)
  const stale = due.getByRole('article', { name: TWICE.statement })
  await expect(stale).toBeVisible()
  const above =
    ((await due.boundingBox())?.y ?? Infinity) < ((await core(writesBoard).boundingBox())?.y ?? 0)

  expect(above).toBe(true)
  await expect(due.getByRole('article')).toHaveCount(1)
  await expect(stale.getByText('Review was due 1 Apr 2020')).toBeVisible()
  await stale.getByRole('button', { name: 'Still holds' }).click()

  await expect(due).toHaveCount(0)
  await expect(writesBoard.getByText('Nothing to review', { exact: true })).toBeVisible()
  expect((await served.api('GET', entryPath(staleId))).json).toMatchObject({ reviewed: TODAY })
})

test('e2e_keyboard_focus_follows_a_memory_form_that_opens_and_closes', async ({
  served,
  writesBoard,
}) => {
  seedMemory(served, [TWICE])
  await writesBoard.goto(`${served.url}/memory`)
  const twice = reviewDue(writesBoard).getByRole('article', { name: TWICE.statement })
  const retire = twice.getByRole('button', { name: 'Retire' })
  await retire.focus()
  await writesBoard.keyboard.press('Enter')

  await expect(twice.getByRole('textbox', { name: 'Why it no longer applies' })).toBeFocused()
  await twice.getByRole('button', { name: 'Cancel' }).click()
  await expect(retire).toBeFocused()

  const add = writesBoard.getByRole('button', { name: 'Add an entry' })
  await add.focus()
  await writesBoard.keyboard.press('Enter')
  const form = writesBoard.getByRole('form', { name: 'Add an entry' })
  await expect(form.getByRole('textbox', { name: 'Statement' })).toBeFocused()
  await form.getByRole('button', { name: 'Cancel' }).click()
  await expect(add).toBeFocused()
})
