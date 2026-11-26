// CF-1163 acceptance flow: the owner writes an agent's context on the Agents page, sees its count,
// is refused one too long and restores an earlier version, served by the server over the
// writes sample state with a stand-in agent.

import { readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import type { Page } from '@playwright/test'
import { TIMEOUT, expect, test, toasts, drawnIn, type Served } from './fixtures'

/** agents.json holding `writer`, with `extra` fields, before the page reads it. */
function writer(served: Served, extra: object = {}): void {
  writeFileSync(
    join(served.home, 'agents.json'),
    JSON.stringify([{ name: 'writer', runtime: 'claude', roles: ['spec'], ...extra }]),
  )
}

const agents = (served: Served) =>
  JSON.parse(readFileSync(join(served.home, 'agents.json'), 'utf8'))

async function editWriter(page: Page) {
  await page
    .getByRole('navigation', { name: 'Pages' })
    .getByRole('link', { name: 'Agents' })
    .click()
  const card = page
    .getByRole('region', { name: /^Agents/ })
    .getByRole('listitem', { name: 'writer' })
  await card.waitFor({ timeout: TIMEOUT })
  await card.getByRole('button', { name: 'Edit writer' }).click()
  const form = card.getByRole('form', { name: 'Edit writer' })
  return { card, form, context: form.getByRole('textbox', { name: 'Context' }) }
}

// CF-1163-A1
test('e2e_an_agents_context_is_written_counted_and_kept', async ({ served, writesBoard }) => {
  writer(served)
  const { card, form, context } = await editWriter(writesBoard)

  await context.fill('Keep each step small.')
  await expect(form.getByText('21 of 8,000 characters')).toBeVisible()
  await form.getByRole('button', { name: 'Save' }).click()

  await expect(toasts(writesBoard).getByText('Saved writer')).toBeVisible()
  await expect(card.getByText('Context: 21 characters, its next run receives it')).toBeVisible()
  expect(agents(served)[0]).toMatchObject({ name: 'writer', context: 'Keep each step small.' })
  await card.getByRole('button', { name: 'Edit writer' }).click()
  await expect(card.getByRole('textbox', { name: 'Context' })).toHaveValue('Keep each step small.')
})

// CF-1163-A2
test('e2e_an_overlong_context_is_refused_on_the_page', async ({ served, writesBoard }) => {
  writer(served)
  const { form, context } = await editWriter(writesBoard)
  const pasted = 'x'.repeat(8214)

  await context.fill(pasted)
  const count = form.getByText('8,214 of 8,000 characters, 214 over')
  expect(await drawnIn(count, 'destructive')).toBe(true)
  await form.getByRole('button', { name: 'Save' }).click()

  await expect(
    form.getByText("context is 8,214 characters; an agent's context holds at most 8,000"),
  ).toBeVisible()
  await expect(context).toHaveValue(pasted)
  await expect(context).toHaveAttribute('aria-invalid', 'true')
  expect(agents(served)[0].context).toBeUndefined()
})

// CF-1163-A3
test('e2e_a_context_version_is_restored_from_history', async ({ served, writesBoard }) => {
  writer(served, {
    context: 'Second words.',
    context_at: 1_790_000_600,
    context_history: [{ at: 1_790_000_000, context: 'First words.' }],
  })
  const { form, context } = await editWriter(writesBoard)

  const history = form.getByText('History (1 earlier version)')
  await history.click()
  await expect(form.getByText(/· 12 characters/)).toBeVisible()
  await form.getByRole('button', { name: /^Restore the version of / }).click()

  await expect(toasts(writesBoard).getByText(/^Restored writer's context of/)).toBeVisible()
  await expect(toasts(writesBoard).getByRole('button', { name: 'Undo' })).toBeVisible()
  await expect(context).toHaveValue('First words.')
  await expect(form.getByText(/· 13 characters/)).toBeVisible()
  expect(agents(served)[0]).toMatchObject({
    context: 'First words.',
    context_history: [{ at: 1_790_000_600, context: 'Second words.' }],
  })
})

// CF-1163-A7
test('e2e_the_context_preview_renders_markdown', async ({ served, writesBoard }) => {
  writer(served)
  const { form, context } = await editWriter(writesBoard)
  const typed =
    '# Steps\n- one\n\n`cargo test`\n\n<script>window.ran = 1</script><img src=x onerror="window.ran = 2">'

  await context.fill(typed)
  await form.getByRole('tab', { name: 'Preview' }).click()
  const preview = form.getByRole('tabpanel', { name: 'Preview' })

  await expect(preview.getByRole('heading', { name: 'Steps' })).toBeVisible()
  await expect(preview.getByRole('listitem')).toHaveText('one')
  await expect(preview.getByRole('code')).toHaveText('cargo test')
  await expect(preview).toContainText('<script>window.ran = 1</script><img src=x onerror=')
  expect(await preview.evaluate((panel) => panel.querySelectorAll('script, img').length)).toBe(0)
  expect(await writesBoard.evaluate(() => (window as { ran?: number }).ran)).toBeUndefined()
  await expect(context).toBeHidden()

  await form.getByRole('tab', { name: 'Write' }).click()
  await expect(context).toHaveValue(typed)
  expect(agents(served)[0].context).toBeUndefined()
})
