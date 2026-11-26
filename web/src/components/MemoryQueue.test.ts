// @vitest-environment happy-dom
// CF-1171-R1: a queue shows its first rows and the rest behind one button; the keyboard stays in
// the list when that button goes away.

import { flushPromises, mount } from '@vue/test-utils'
import { h } from 'vue'
import { expect, test } from 'vitest'
import MemoryQueue from './MemoryQueue.vue'

const rows = ['a', 'b', 'c', 'd', 'e']

function queue(withControl: boolean) {
  return mount(MemoryQueue, {
    attachTo: document.body,
    props: { id: 'q', title: 'Queue', rows, keyOf: (r: unknown) => String(r) },
    slots: {
      row: ({ row }: { row: unknown }) =>
        withControl
          ? h('button', { type: 'button' }, `Apply ${String(row)}`)
          : h('span', String(row)),
    },
  })
}
const more = (wrapper: ReturnType<typeof queue>) => {
  const found = wrapper.findAll('button').find((b) => b.text().startsWith('Show'))
  if (!found) throw new Error('the Show more button is missing')
  return found
}

test('show_more_moves_focus_to_the_first_newly_shown_rows_control', async () => {
  const wrapper = queue(true)
  more(wrapper).element.focus()

  await more(wrapper).trigger('click')
  await flushPromises()

  expect(document.activeElement?.textContent).toBe('Apply d')
  wrapper.unmount()
})

test('show_more_focuses_the_first_newly_shown_row_when_it_has_no_control', async () => {
  const wrapper = queue(false)
  more(wrapper).element.focus()

  await more(wrapper).trigger('click')
  await flushPromises()

  expect(document.activeElement?.tagName).toBe('LI')
  expect(document.activeElement?.textContent).toBe('d')
  wrapper.unmount()
})
