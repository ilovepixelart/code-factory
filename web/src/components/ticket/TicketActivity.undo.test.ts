// @vitest-environment happy-dom

import type { VueWrapper } from '@vue/test-utils'
import { afterEach, expect, test, vi } from 'vitest'
import { BASE, form, view } from '../../test/ticketForm'

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

const NOW = 1_791_108_660
const edit = (at: number, from: string, to: string) => ({
  at,
  sentence: `coordinator set priority from ${from} to ${to}`,
  kind: 'coordinator_edit',
  text: '',
  edit: { name: 'priority', from, to },
})

async function shown(held: string, entries: object[]) {
  const ticket = { ...(view as { ticket: object }).ticket, priority: held }
  return form({ ...(view as object), ticket, activity: entries })
}

const undoButtons = (page: VueWrapper) => page.findAll('button').filter((b) => b.text() === 'Undo')

// CF-1428-R2: the latest coordinator edit of a field, while the card holds what it set, has Undo,
// which posts the field's name to the ticket's coordinator-undo.
test('the_latest_edit_offers_undo_and_posts_the_field', async () => {
  const { page, changes, bodies } = await shown('high', [edit(NOW - 10, 'low', 'high')])

  const buttons = undoButtons(page)
  await buttons[0]?.trigger('click')

  expect(buttons).toHaveLength(1)
  expect(changes).toEqual([`POST ${BASE}/coordinator-undo`])
  expect(bodies).toEqual([{ name: 'priority' }])
  page.unmount()
})

// CF-1428-R3: no Undo once the field holds something else, and none on an older edit of the field.
test('undo_is_not_offered_after_a_later_change_or_on_an_older_edit', async () => {
  // One ticket at a time: two forms of the same ticket share its one read.
  const changed = await shown('urgent', [edit(NOW - 10, 'low', 'high')])
  const afterChange = undoButtons(changed.page).length
  changed.page.unmount()
  const older = await shown('medium', [
    edit(NOW - 10, 'high', 'medium'),
    edit(NOW - 20, 'low', 'high'),
  ])
  const onOlder = undoButtons(older.page).length
  older.page.unmount()

  expect(afterChange).toBe(0)
  expect(onOlder).toBe(1)
})
