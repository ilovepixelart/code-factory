// @vitest-environment happy-dom
// The ticket's header says its stage and what holds it as the board's cards do: each status word
// starts with a capital (docs/design.md).

import { afterEach, expect, test, vi } from 'vitest'
import { form, view } from '../test/ticketForm'

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

test('the_header_says_blocked_with_a_capital_beside_the_stage', async () => {
  const blocked = {
    ...(view as object),
    current_stage: 'build',
    ticket: { ...(view as { ticket: object }).ticket, blocked: 'waits for the vendor' },
  }
  const { page } = await form(blocked)

  const badges = page.findAll('[data-slot="badge"]').map((b) => b.text().trim())
  expect(badges).toContain('Blocked')
  expect(badges).not.toContain('blocked')
  page.unmount()
})

// The stage reads as its glyph and words, with what holds it, not as one more badge beside the
// status badges.
test('the_header_names_the_stage_with_its_glyph', async () => {
  const { page } = await form({ ...(view as object), current_stage: 'build' })

  const stage = page.get('[data-header-stage]')
  expect({
    glyph: stage.find('svg[data-shape="half"]').exists(),
    text: stage.text().trim(),
    badge: stage.attributes('data-slot'),
  }).toEqual({ glyph: true, text: 'In Build · needs a branch', badge: undefined })
  page.unmount()
})
