// CF-271 acceptance flows: reviewing and adding memory entries on the Memory page, served by the
// server over the writes sample state.

import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { type Served, TIMEOUT, expect, test } from './fixtures'

const SMALL =
  '---\nkind: rule\ndate: 2020-01-01\nsource: conversation\nwhy: Small rules are read\n---\nKeep every rule small\n'
const TWICE =
  '---\nkind: lesson\ndate: 2020-01-02\nsource: CF-2\nwhy: It cost a run\nguard: \n---\nRun the gate once\n'

function seed(served: Served): string {
  return served.writeMemory({
    '2026-10-01-keep-every-rule-small.md': SMALL,
    '2026-10-02-run-the-gate-once.md': TWICE,
  })
}

test('e2e_memory_entries_are_reviewed_on_the_page', async ({ served, writesBoard }) => {
  const memory = seed(served)
  await writesBoard.goto(`${served.url}/memory`)
  const due = writesBoard.getByRole('region', { name: /^Review due\b/ })
  const small = due.getByRole('article', { name: 'Keep every rule small' })
  await small.waitFor({ timeout: TIMEOUT })
  await small.getByRole('button', { name: 'Still holds' }).click()
  await small.waitFor({ state: 'detached', timeout: TIMEOUT })
  const twice = due.getByRole('article', { name: 'Run the gate once' })
  await twice.getByRole('button', { name: 'Retire' }).click()
  await twice.getByRole('textbox', { name: 'Why it no longer applies' }).fill('The gate refuses it')
  await twice.getByRole('button', { name: 'Retire' }).click()
  const history = writesBoard.getByRole('region', { name: /^History\b/ })
  await history.getByRole('heading', { name: /^History\s*,\s*1$/ }).click()
  const retired = history.getByRole('listitem', { name: 'Run the gate once' })
  await retired.waitFor({ timeout: TIMEOUT })

  await expect(retired.getByText('The gate refuses it')).toBeVisible()
  await expect(due).toHaveCount(0)
  expect(readFileSync(join(memory, '2026-10-01-keep-every-rule-small.md'), 'utf8')).toMatch(
    /\nreviewed: \d{4}-\d{2}-\d{2}\n/,
  )
  expect(
    readFileSync(join(memory, 'retired', '2026-10-02-run-the-gate-once.md'), 'utf8'),
  ).toContain('\nretired: The gate refuses it\n')
})

test('e2e_a_memory_entry_is_added_from_the_page', async ({ served, writesBoard }) => {
  seed(served)
  await writesBoard.goto(`${served.url}/memory`)
  const meter = writesBoard.getByRole('meter', { name: 'Loaded into every agent session' })
  await writesBoard
    .getByRole('region', { name: /^Core\b/ })
    .getByRole('listitem', { name: 'Keep every rule small' })
    .waitFor({ timeout: TIMEOUT })
  const before = Number(await meter.getAttribute('value'))
  await writesBoard.getByRole('button', { name: 'Add an entry' }).click()
  const form = writesBoard.getByRole('form', { name: 'Add an entry' })
  await form.getByRole('group', { name: 'Kind' }).getByRole('button', { name: 'Decision' }).click()
  await form.getByRole('textbox', { name: 'Statement' }).fill('Ship one ticket at a time')
  await form.getByRole('textbox', { name: 'Why' }).fill('Parallel tickets collided')
  await expect(form.getByText('Required: where the entry comes from')).toBeVisible()
  await expect(form.getByRole('button', { name: 'Add' })).toBeDisabled()
  await form.getByRole('textbox', { name: 'Source' }).fill('CF-271')
  await form.getByRole('button', { name: 'Add' }).click()
  const added = writesBoard
    .getByRole('region', { name: /^Core\b/ })
    .getByRole('listitem', { name: 'Ship one ticket at a time' })
  await added.waitFor({ timeout: TIMEOUT })
  await added.getByText('Ship one ticket at a time').click()

  await expect(added.getByText('Why: Parallel tickets collided')).toBeVisible()
  await expect.poll(async () => Number(await meter.getAttribute('value'))).toBeGreaterThan(before)
  await expect(meter).toHaveAttribute('max', '8000')
})

const EARLIER =
  '---\nkind: rule\ndate: 2026-10-01\nsource: CF-131\nwhy: It happened\nreviewed: 2026-10-01\n---\nRun the gate before every push of a ticket branch\n'
const LATER =
  '---\nkind: rule\ndate: 2026-10-05\nsource: chat\nwhy: It happened\nreviewed: 2026-10-05\n---\nRun the gate before each push of the ticket branch\n'

// CF-978-R2, CF-978-R3 (CF-978-A1): a proposal is listed in the command's words and applied.
test('e2e_the_memory_page_lists_and_applies_a_proposal', async ({ served, writesBoard }) => {
  served.writeMemory({
    '2026-10-01-run-the-gate.md': EARLIER,
    '2026-10-05-run-the-gate-each.md': LATER,
  })
  await writesBoard.goto(`${served.url}/memory`)
  const section = writesBoard.getByRole('region', { name: /^Proposed by consolidate\b/ })
  const words =
    'Merge "Run the gate before each push of the ticket branch" into "Run the gate before every push of a ticket branch"'
  await expect(section.getByText(words)).toBeVisible({ timeout: TIMEOUT })

  await section.getByRole('button', { name: 'Apply' }).click()

  await expect(writesBoard.getByRole('button', { name: 'Undo' })).toBeVisible({ timeout: TIMEOUT })
  await expect(section).toHaveCount(0, { timeout: TIMEOUT })
})

const TODAY = new Date().toISOString().slice(0, 10)
const FRESH = `---\nkind: rule\ndate: ${TODAY}\nsource: chat\nwhy: Small rules are read\nreviewed: ${TODAY}\n---\nKeep every rule small\n`
const STALE =
  '---\nkind: lesson\ndate: 2020-01-02\nsource: CF-2\nwhy: It cost a run\nreviewed: 2020-01-02\n---\nRun the gate once\n'

// CF-1171-R1, CF-1171-R5 (CF-1171-A1): what needs a review is above the entries, and Still holds
// empties the queue.
test('e2e_review_due_comes_first_and_empties_when_reviewed', async ({ served, writesBoard }) => {
  const memory = served.writeMemory({
    '2026-10-01-keep-every-rule-small.md': FRESH,
    '2026-10-02-run-the-gate-once.md': STALE,
  })
  await writesBoard.goto(`${served.url}/memory`)
  const due = writesBoard.getByRole('region', { name: /^Review due\b/ })
  const stale = due.getByRole('article', { name: 'Run the gate once' })
  await stale.waitFor({ timeout: TIMEOUT })
  const core = writesBoard.getByRole('region', { name: /^Core\b/ })
  const above = ((await due.boundingBox())?.y ?? Infinity) < ((await core.boundingBox())?.y ?? 0)
  const listed = await due.getByRole('article').count()
  const since = await stale.getByText('review was due 1 Apr 2020').isVisible()

  await stale.getByRole('button', { name: 'Still holds' }).click()
  await due.waitFor({ state: 'detached', timeout: TIMEOUT })

  expect([above, listed, since]).toStrictEqual([true, 1, true])
  await expect(
    writesBoard.getByText('Nothing needs you: no proposals, no flags, nothing due for review.'),
  ).toBeVisible()
  expect(readFileSync(join(memory, '2026-10-02-run-the-gate-once.md'), 'utf8')).toContain(
    `\nreviewed: ${TODAY}\n`,
  )
})

test('e2e_keyboard_focus_follows_a_memory_form_that_opens_and_closes', async ({
  served,
  writesBoard,
}) => {
  seed(served)
  await writesBoard.goto(`${served.url}/memory`)
  const due = writesBoard.getByRole('region', { name: /^Review due\b/ })
  const twice = due.getByRole('article', { name: 'Run the gate once' })
  await twice.waitFor({ timeout: TIMEOUT })
  await twice.getByRole('button', { name: 'Retire' }).focus()
  await writesBoard.keyboard.press('Enter')

  await expect(twice.getByRole('textbox', { name: 'Why it no longer applies' })).toBeFocused()
  await twice.getByRole('button', { name: 'Cancel' }).click()
  await expect(twice.getByRole('button', { name: 'Retire' })).toBeFocused()

  await writesBoard.getByRole('button', { name: 'Add an entry' }).focus()
  await writesBoard.keyboard.press('Enter')
  await expect(writesBoard.getByRole('textbox', { name: 'Statement' })).toBeFocused()
})
