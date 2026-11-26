// @vitest-environment happy-dom
// A tab panel is a Tab stop, so a keyboard user sees where focus is when it lands there.

import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import { defineComponent } from 'vue'
import { Tabs, TabsContent } from '.'

test('a_focused_panel_draws_the_focus_ring', () => {
  const view = mount(
    defineComponent({
      components: { Tabs, TabsContent },
      template: '<Tabs default-value="a"><TabsContent value="a">Text</TabsContent></Tabs>',
    }),
  )
  const panel = view.get('[data-slot="tabs-content"]')

  expect(panel.attributes('tabindex')).toBe('0')
  expect(panel.classes()).toEqual(
    expect.arrayContaining(['focus-visible:ring-3', 'focus-visible:ring-ring/50']),
  )
})
