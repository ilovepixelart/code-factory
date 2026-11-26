// CF-358 acceptance flow: agents are added, changed and removed on the Agents page, served by
// the server over the writes sample state with a stand-in agent.

import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { TIMEOUT, expect, test, toasts } from './fixtures'

test('e2e_an_agent_is_added_changed_and_removed', async ({ served, writesBoard }) => {
  const file = join(served.home, 'agents.json')
  const notice = toasts(writesBoard)
  await writesBoard
    .getByRole('navigation', { name: 'Pages' })
    .getByRole('link', { name: 'Agents' })
    .click()
  await writesBoard.getByRole('button', { name: 'New agent' }).click()
  const form = writesBoard.getByRole('form', { name: 'New agent' })
  await form.getByRole('textbox', { name: 'Name' }).fill('writer')
  await form.getByRole('combobox', { name: 'Harness' }).selectOption('claude')
  await form.getByRole('checkbox', { name: 'Spec' }).check()
  await form.getByRole('button', { name: 'Add' }).click()
  const list = writesBoard.getByRole('region', { name: /^Agents/ })
  const writer = list.getByRole('listitem', { name: 'writer' })
  await writer.waitFor({ timeout: TIMEOUT })

  await expect(writer.getByText('Spec')).toBeVisible()
  await expect(notice.getByText('Added writer')).toBeVisible()
  expect(JSON.parse(readFileSync(file, 'utf8'))).toMatchObject([
    { name: 'writer', roles: ['spec'] },
  ])

  await writer.getByRole('button', { name: 'Edit' }).click()
  const edit = writer.getByRole('form', { name: 'Edit writer' })
  await edit.getByRole('combobox', { name: 'Model' }).fill('m-2')
  await edit.getByRole('button', { name: 'Save' }).click()

  await expect(writer.getByText('m-2')).toBeVisible()
  await expect(notice.getByText('Saved writer')).toBeVisible()

  await writer.getByLabel('More actions for writer').click()
  await writer.getByRole('button', { name: 'Remove' }).click()

  await expect(list.getByRole('listitem')).toHaveCount(0)
  await expect(notice.getByText('Removed writer')).toBeVisible()
  expect(existsSync(file) ? JSON.parse(readFileSync(file, 'utf8')) : []).toStrictEqual([])
})

// CF-1273: the types and labels an agent takes are set on its form, written to agents.json and
// said on its card.
test('e2e_an_agent_is_limited_to_ticket_types_and_labels', async ({ served, writesBoard }) => {
  const file = join(served.home, 'agents.json')
  await writesBoard
    .getByRole('navigation', { name: 'Pages' })
    .getByRole('link', { name: 'Agents' })
    .click()
  await writesBoard.getByRole('button', { name: 'New agent' }).click()
  const form = writesBoard.getByRole('form', { name: 'New agent' })
  await form.getByRole('textbox', { name: 'Name' }).fill('scribe')
  await form.getByRole('checkbox', { name: 'Build' }).check()
  await form.getByRole('checkbox', { name: 'docs' }).check()
  await form.getByRole('textbox', { name: 'Ticket labels' }).fill('ui, web')
  await form.getByRole('button', { name: 'Add' }).click()
  const scribe = writesBoard.getByRole('listitem', { name: 'scribe' })
  await scribe.waitFor({ timeout: TIMEOUT })

  await expect(scribe.getByText('Takes only types docs · labels ui, web')).toBeVisible()
  expect(JSON.parse(readFileSync(file, 'utf8'))).toMatchObject([
    { name: 'scribe', types: ['docs'], labels: ['ui', 'web'] },
  ])
})
