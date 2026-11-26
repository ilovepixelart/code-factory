// CF-1206: the ticket page orders its sections by use: Status with its next action, questions,
// Description, Agent and checks, Activity; Documents, Screens and Links after.

import { afterEach, expect, test, vi } from 'vitest'
import { form, view } from '../../support/ticketForm'

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

test('the_sections_follow_the_order_of_use', async () => {
  const ui = {
    ...(view as object),
    ticket: { ...(view as { ticket: object }).ticket, labels: 'ui' },
  }
  const { page } = await form(ui)

  const headings = page.findAll('[data-slot="section-heading"]').map((h) => h.attributes('id'))
  const rank = (name: string) => headings.indexOf(name)

  // Where the ticket stands is part of its header, under the title, before every section.
  const status = page.get('section[aria-label="Status"]').element
  const first = page.get('[data-slot="section-heading"]').element
  expect(status.compareDocumentPosition(first) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  const before = ['description-heading', 'agent-heading', 'activity-heading']
  const after = ['documents-heading', 'screens-heading', 'links-heading']
  const order = [...before, ...after].map(rank)
  expect(
    order.every((n) => n >= 0),
    headings.join(','),
  ).toBe(true)
  expect(order).toEqual([...order].sort((a, b) => a - b))
  page.unmount()
})

// The Description switches between Write and Preview as an agent's Context does: the same tabs,
// Write first (docs/ui.md: line tabs are only the ticket's content panes).
test('the_description_offers_write_then_preview_in_the_default_tabs', async () => {
  const { page } = await form()

  const section = page.get('section[aria-labelledby="description-heading"]')
  const list = section.get('[data-slot="tabs-list"]')

  expect(list.findAll('[role="tab"]').map((t) => t.text())).toEqual(['Write', 'Preview'])
  expect(list.attributes('data-variant')).toBe('default')
  page.unmount()
})
