// CF-1292: a single line value is cut by CSS, never trimmed, and its whole text is in a tooltip.

import { flushPromises, mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import CutText from '@/components/CutText.vue'

test('a_cut_text_shows_all_of_its_text_and_its_tooltip_holds_it_whole', async () => {
  const text = `ticket/${'b'.repeat(60)}`
  const cut = mount(CutText, { props: { text }, attachTo: document.body })
  const trigger = cut.get('[data-slot="tooltip-trigger"]')

  expect(trigger.text()).toBe(text)
  expect(document.querySelector('[data-slot="tooltip-content"]')).toBeNull()
  await trigger.trigger('focus')
  await flushPromises()

  expect(document.querySelector('[data-slot="tooltip-content"]')?.textContent).toContain(text)
  cut.unmount()
})

test('classes_given_to_a_cut_text_reach_its_box', () => {
  const cut = mount(CutText, { props: { text: 'main' }, attrs: { class: 'font-medium' } })

  expect(cut.classes()).toContain('font-medium')
})
