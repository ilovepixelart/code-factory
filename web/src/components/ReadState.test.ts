// @vitest-environment happy-dom
// A page being read shows the outline of its sections as Skeletons, and says what it reads to a
// screen reader; a failed read keeps its reason and Read again.

import { mount } from '@vue/test-utils'
import { describe, expect, test } from 'vitest'
import ReadState from './ReadState.vue'

describe('a page being read', () => {
  test('it_shows_skeletons_in_the_pages_shape_and_no_spinner', () => {
    const view = mount(ReadState, { props: { what: 'the archive', shape: 'table' } })

    expect(view.get('[data-read-shape]').attributes('data-read-shape')).toBe('table')
    expect(view.findAll('[data-slot="skeleton"]').length).toBeGreaterThan(1)
    expect(view.find('[data-slot="spinner"], [role="status"]').exists()).toBe(false)
  })

  test('it_says_what_it_reads_politely_while_busy', () => {
    const view = mount(ReadState, { props: { what: 'the archive' } })
    const region = view.get('[aria-live="polite"]')

    expect([region.text(), region.attributes('aria-busy')]).toEqual(['Reading the archive', 'true'])
  })

  test('a_page_that_names_no_shape_reads_as_a_document', () => {
    const view = mount(ReadState, { props: { what: 'the ticket' } })

    expect(view.get('[data-read-shape]').attributes('data-read-shape')).toBe('document')
  })

  test('a_failed_read_shows_its_reason_and_read_again_without_skeletons', async () => {
    const view = mount(ReadState, {
      props: { what: 'the archive', shape: 'table', failed: 'The archive could not be read' },
    })

    await view.get('[data-read-again]').trigger('click')

    expect(view.get('[data-slot="alert"]').text()).toContain('The archive could not be read')
    expect(view.find('[data-slot="skeleton"]').exists()).toBe(false)
    expect(view.emitted('retry')).toHaveLength(1)
  })
})
