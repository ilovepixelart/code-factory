// CF-918 acceptance flows: the Agents page names the guarantees a harness lacks, from the list the
// real route answers, served by the server with a stand-in agent.

import { writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { Served, TIMEOUT, expect, serve, test as base } from './fixtures'

const test = base.extend<{ pair: Served }>({
  pair: async ({}, use) => {
    const { served, stop } = await serve('writes', 'false', false)
    writeFileSync(
      join(served.home, 'agents.json'),
      JSON.stringify([
        { name: 'builder', runtime: 'codex', roles: ['build'] },
        { name: 'writer', runtime: 'claude', roles: ['spec'] },
      ]),
    )
    await use(served)
    stop()
  },
})

// CF-918-A1
test('e2e_an_agent_card_names_what_its_harness_lacks', async ({ pair, page }) => {
  await page.goto(`${pair.url}/agents`)
  const builder = page.getByRole('listitem', { name: 'builder' })
  await builder.waitFor({ timeout: TIMEOUT })

  await expect(builder.getByText('Lacks: permission requests reach the Inbox')).toBeVisible()
  await expect(builder.getByText('permission requests reach the Inbox')).toHaveAttribute(
    'title',
    /codex's user input request .* reaches the Inbox as a question of the ticket/,
  )
  await expect(page.getByRole('listitem', { name: 'writer' })).not.toContainText('Lacks:')
})

// CF-918-A2
test('e2e_the_agent_form_lists_what_the_picked_harness_lacks', async ({ pair, page }) => {
  await page.goto(`${pair.url}/agents`)
  await page.getByRole('button', { name: 'New agent' }).click()
  const form = page.getByRole('form', { name: 'New agent' })
  const harness = form.getByRole('combobox', { name: 'Harness' })

  await harness.selectOption('omp')

  await expect(form.getByText('This harness lacks:')).toBeVisible()
  await expect(form.getByRole('listitem')).toHaveCount(1)
  await expect(form.getByRole('listitem')).toContainText('permission requests reach the Inbox')

  await harness.selectOption('claude')

  await expect(form.getByText('This harness lacks:')).toBeHidden()
  await expect(form.getByRole('listitem')).toHaveCount(0)
})
