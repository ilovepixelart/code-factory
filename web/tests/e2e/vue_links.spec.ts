// CF-253 acceptance flows: managing a ticket's relationships from its Links section, over the
// writes sample state (CF-3 "Declared" is CF-1's child there).

import type { Locator, Page } from '@playwright/test'
import { Served, TIMEOUT, expect, test } from './fixtures'

async function links(page: Page, served: Served, id: string): Promise<Locator> {
  await page.goto(`${served.url}/tickets/sample/${id}`)
  const section = page.getByRole('region', { name: 'Links', exact: true })
  await section.waitFor({ timeout: TIMEOUT })
  return section
}

test('e2e_the_links_section_lists_and_removes_children', async ({ served, writesBoard }) => {
  const section = await links(writesBoard, served, 'CF-1')
  const children = section.getByRole('list', { name: 'Children' })
  await children.getByText('Declared').waitFor({ timeout: TIMEOUT })
  const text = await children.innerText()

  await children.getByRole('button', { name: 'Remove CF-3 from Children' }).click()
  await expect.poll(() => served.ticket('CF-3'), { timeout: TIMEOUT }).not.toContain('parent:')
  await section.getByText('No links yet.').waitFor({ timeout: TIMEOUT })

  expect(text).toContain('CF-3')
  expect(text).toContain('Declared')
  expect(text).toContain('Build')
})

test('e2e_a_link_is_added_from_the_links_section', async ({ served, writesBoard }) => {
  const section = await links(writesBoard, served, 'CF-1')
  await section.getByRole('button', { name: 'Link a ticket' }).click()
  await section
    .getByRole('group', { name: 'Link kind' })
    .getByRole('button', { name: 'Blocked by' })
    .click()
  const find = section.getByRole('combobox', { name: 'Find a ticket by id or title' })
  await find.fill('Declared')
  await section.getByRole('option', { name: /CF-3/ }).waitFor({ timeout: TIMEOUT })
  await find.press('Enter')
  await expect.poll(() => served.ticket('CF-1'), { timeout: TIMEOUT }).toContain('blocked_by: CF-3')
  await section
    .getByRole('list', { name: 'Blocked by' })
    .getByText('CF-3')
    .waitFor({ timeout: TIMEOUT })

  await section.getByRole('button', { name: 'Link a ticket' }).click()
  await section
    .getByRole('group', { name: 'Link kind' })
    .getByRole('button', { name: 'Parent' })
    .click()
  // The picker is open and lists the other tickets until the search narrows it.
  await expect(section.getByRole('option', { name: /CF-2\b/ })).toBeVisible()
  await find.fill('Specs written')
  await expect(find).toHaveAttribute('aria-expanded', 'false')

  await expect(section.getByRole('option', { name: /CF-1\b/ })).toHaveCount(0)
})

test('e2e_the_link_picker_takes_focus_and_gives_it_back', async ({ served, writesBoard }) => {
  const section = await links(writesBoard, served, 'CF-1')
  const opener = section.getByRole('button', { name: 'Link a ticket' })
  const find = section.getByRole('combobox', { name: 'Find a ticket by id or title' })

  await opener.click()
  await expect(find).toBeFocused()
  await find.press('Escape')
  await expect(find).toHaveCount(0)
  await expect(opener).toBeFocused()

  await opener.click()
  await find.fill('Declared')
  await section.getByRole('option', { name: /CF-3/ }).waitFor({ timeout: TIMEOUT })
  await find.press('Enter')
  await expect(find).toHaveCount(0, { timeout: TIMEOUT })
  await expect(opener).toBeFocused()
})
