// CF-224 acceptance flows: the new ticket dialog of the Vue board, served by the server over
// the writes sample state.

import type { Locator, Page } from '@playwright/test'
import { TIMEOUT, card, expect, test, toasts, addLabels } from './fixtures'

const FEATURE = '## Goal\n\nWhat it lets someone do.\n'
const BUG = '## Steps\n\n1. \n\n## Expected\n\n## Actual\n'

function dialog(page: Page): Locator {
  return page.getByRole('dialog', { name: 'New ticket' })
}

test('e2e_a_ticket_is_created_from_the_dialog', async ({ served, writesBoard }) => {
  await writesBoard.keyboard.press('n')
  const form = dialog(writesBoard)
  await form.waitFor({ timeout: TIMEOUT })
  const description = form.getByRole('textbox', { name: 'Description' })
  await expect.poll(() => description.inputValue()).toBe(FEATURE)
  await expect(form.getByRole('textbox', { name: 'Title', exact: true })).toBeFocused()
  await expect(form.getByLabel('Repository').getByRole('option')).toHaveText(['sample', 'second'])
  await form.getByLabel('Type').selectOption('bug')
  await expect.poll(() => description.inputValue()).toBe(BUG)
  await writesBoard.keyboard.type('Crash on save')
  await addLabels(form, 'ui', 'data')
  await form.getByRole('button', { name: 'Create ticket' }).click()
  await form.waitFor({ state: 'hidden', timeout: TIMEOUT })
  await card(writesBoard, 'CF-5').waitFor({ timeout: TIMEOUT })
  await expect(toasts(writesBoard)).toContainText(/Created CF-5/)
  const text = served.ticket('CF-5')

  expect(text).toContain('title: Crash on save')
  expect(text).toContain('type: bug')
  expect(text).toContain('labels: ui, data')
  expect(text.endsWith('## Steps\n\n1. \n\n## Expected\n\n## Actual\n')).toBe(true)
})

test('e2e_a_dismissed_draft_is_kept_and_a_created_one_is_not', async ({ writesBoard }) => {
  await writesBoard.keyboard.press('n')
  const form = dialog(writesBoard)
  const title = form.getByRole('textbox', { name: 'Title', exact: true })
  const description = form.getByRole('textbox', { name: 'Description' })
  await expect.poll(() => description.inputValue()).toBe(FEATURE)
  await title.fill('Half typed')
  await description.fill('My own words.')
  await writesBoard.keyboard.press('Escape')
  await form.waitFor({ state: 'hidden', timeout: TIMEOUT })
  await writesBoard.keyboard.press('n')
  await form.waitFor({ timeout: TIMEOUT })

  await expect(title).toHaveValue('Half typed')
  await expect(description).toHaveValue('My own words.')

  await form.getByRole('button', { name: 'Create ticket' }).click()
  await form.waitFor({ state: 'hidden', timeout: TIMEOUT })
  await writesBoard.keyboard.press('n')
  await form.waitFor({ timeout: TIMEOUT })

  await expect(title).toHaveValue('')
  await expect.poll(() => description.inputValue()).toBe(FEATURE)
})

test('e2e_an_edited_description_is_kept', async ({ served, writesBoard }) => {
  await writesBoard.getByRole('button', { name: 'New ticket' }).click()
  const form = dialog(writesBoard)
  const description = form.getByRole('textbox', { name: 'Description' })
  await expect.poll(() => description.inputValue()).toBe(FEATURE)
  await description.fill('My own words.')
  const template = writesBoard.waitForResponse((r) => r.url().endsWith('/templates/bug'), {
    timeout: TIMEOUT,
  })
  await form.getByLabel('Type').selectOption('bug')
  // The bug template arrives and is passed over: the description is no longer a template.
  await (await template).finished()

  await expect(description).toHaveValue('My own words.')
  expect(served.ticket('CF-5')).toBe('')
})

test('e2e_a_refused_ticket_keeps_the_dialog', async ({ served, writesBoard }) => {
  await writesBoard.getByRole('button', { name: 'New ticket' }).click()
  const form = dialog(writesBoard)
  await form.getByRole('textbox', { name: 'Title' }).fill('Too far')
  await form.getByLabel('Type').selectOption('bug')
  await form.getByLabel('Caused by').fill('CF-9999')
  await form.getByRole('button', { name: 'Create ticket' }).click()
  await form.getByRole('alert').getByText('no ticket CF-9999').waitFor({ timeout: TIMEOUT })
  // The refusal is handled to its end, where a created ticket would close the dialog.
  await expect(form.getByRole('button', { name: 'Create ticket' })).toBeEnabled()
  await expect(form).toBeVisible()
  await expect(form.getByRole('textbox', { name: 'Title' })).toHaveValue('Too far')
  await expect(form.getByLabel('Caused by')).toHaveValue('CF-9999')
  await form.getByRole('button', { name: 'Cancel' }).click()
  await form.waitFor({ state: 'hidden', timeout: TIMEOUT })

  expect(served.ticket('CF-5')).toBe('')
})

// CF-817-R3: with a ticket's panel open on the board, the board's sheet and the panel's child
// sheet are both in the page, and no id is used twice.
test('e2e_no_id_is_used_twice_with_a_panel_open', async ({ writesBoard }) => {
  await card(writesBoard, 'CF-2').getByRole('link', { name: 'Bare' }).click()
  await writesBoard.getByRole('button', { name: 'New child ticket' }).waitFor({ timeout: TIMEOUT })

  const repeated = await writesBoard.evaluate(() => {
    const ids = [...document.querySelectorAll('[id]')].map((e) => e.id)
    return [...new Set(ids.filter((id, i) => ids.indexOf(id) !== i))]
  })

  expect(repeated).toStrictEqual([])
})

test('e2e_an_empty_title_is_refused_in_the_page', async ({ served, writesBoard }) => {
  await writesBoard.keyboard.press('n')
  const form = dialog(writesBoard)
  await form.waitFor({ timeout: TIMEOUT })
  const title = form.getByRole('textbox', { name: 'Title', exact: true })
  await form.getByRole('button', { name: 'Create ticket' }).click()

  await expect(form.getByRole('alert')).toHaveText('Give the ticket a title')
  await expect(title).toHaveAttribute('aria-invalid', 'true')
  await expect(title).toBeFocused()
  await expect(form).toBeVisible()
  expect(served.ticket('CF-5')).toBe('')
})
