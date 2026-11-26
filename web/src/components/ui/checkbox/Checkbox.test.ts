// @vitest-environment happy-dom
// A box that holds some of its rows draws a dash, not the tick of one that holds them all.

import { flushPromises, mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import { Checkbox } from '.'

const mark = async (modelValue: boolean | 'indeterminate') => {
  const view = mount(Checkbox, { props: { modelValue } })
  await flushPromises()
  return view.find('[data-mark]').attributes('data-mark')
}

test('some_rows_draw_a_dash_and_all_rows_a_tick', async () => {
  expect(await mark('indeterminate')).toBe('some')
  expect(await mark(true)).toBe('all')
})
