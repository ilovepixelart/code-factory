// @vitest-environment happy-dom
// A page's section is flat on the inset panel (docs/design.md, Page anatomy): a heading row with
// the title, its count and the section's action, then what it holds. Space separates adjacent
// sections. The description is no line of its own: an
// info mark beside the title shows it, and it describes the section to a screen reader.

import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import { h } from 'vue'
import SectionCard from './SectionCard.vue'

const section = (heading: string) =>
  h(
    SectionCard,
    { heading, title: 'Sessions', count: 2, description: 'by repository' },
    { default: () => h('p', 'rows'), action: () => h('button', 'Show ended') },
  )

test('a_section_is_flat_with_its_heading_row_and_no_card_around_it', () => {
  const view = mount(section('sessions-heading'))
  const head = view.get('[data-section-head]')

  const about = head.get('[data-slot="section-description"]')

  expect({
    card: view.find('[data-slot="card"]').exists(),
    title: head.get('h2#sessions-heading').text().replace(/\s+/g, ' '),
    action: head.get('[data-slot="section-action"] button').text(),
    body: view.get('[data-section-body]').text(),
  }).toEqual({ card: false, title: 'Sessions, 2', action: 'Show ended', body: 'rows' })
  expect({
    hidden: about.classes(),
    words: about.text(),
    describes: view.get('section').attributes('aria-describedby') === about.attributes('id'),
    mark: head.get('[data-section-about]').attributes('title'),
    stops: head.findAll('h2 button, h2 [tabindex]').length,
  }).toEqual({
    hidden: ['sr-only'],
    words: 'by repository',
    describes: true,
    mark: 'by repository',
    stops: 0,
  })
})

test('a_section_without_a_description_has_no_info_mark', () => {
  const view = mount(h(SectionCard, { heading: 'plain', title: 'Plain' }))

  expect(view.find('[data-section-about]').exists()).toBe(false)
})

test('a_section_empty_state_has_its_own_card_surface', () => {
  const view = mount(SectionCard, {
    props: { heading: 'sessions', title: 'Sessions', empty: true },
    slots: { empty: 'No live sessions' },
  })

  expect(view.get('[data-section-empty]').attributes('data-slot')).toBe('card')
  expect(view.get('[data-section-empty]').text()).toBe('No live sessions')
})

// This case keeps its original gate identity. The assertion follows the current design.
test('a_hairline_separates_a_section_from_the_one_before_it', () => {
  const page = mount({ render: () => h('div', [section('one'), section('two')]) })
  const [first, second] = page.findAll('[data-section]')

  expect(first?.classes()).toContain('[[data-section]+&]:pt-3')
  expect(first?.classes()).not.toContain('[[data-section]+&]:border-t')
  expect(second?.element.matches('[data-section] + [data-section]')).toBe(true)
})
