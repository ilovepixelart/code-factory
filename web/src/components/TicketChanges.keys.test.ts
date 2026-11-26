// @vitest-environment happy-dom
// docs/ui.md (The kanban), a ticket's Changes: a diff read again after a commit keeps an open
// comment form on the line it was opened on, and a read the board does not answer leaves the rows
// shown and says nothing.

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { clear, notice } from '../lib/notice'
import type { TicketChanges as Changes } from '../lib/ticket'
import { answer, stubFetch } from '../test/board'
import TicketChanges from './TicketChanges.vue'

const diff = (lines: Changes['files'][number]['lines']): Changes => ({
  files: [{ path: 'src/app.ts', lines }],
  cut: false,
  limit: 400,
  branch: 'feature/CF-9',
  default_branch: 'main',
})

const BEFORE = diff([
  { kind: 'kept', number: 1, text: 'import x' },
  { kind: 'removed', number: null, text: 'old()' },
  { kind: 'added', number: 2, text: 'fresh()' },
])
const AFTER = diff([
  { kind: 'added', number: 1, text: 'first()' },
  { kind: 'added', number: 2, text: 'second()' },
  { kind: 'kept', number: 3, text: 'import x' },
  { kind: 'removed', number: null, text: 'old()' },
  { kind: 'added', number: 4, text: 'fresh()' },
])

const SAMPLE = { repository: 'sample', id: 'CF-9' }
const opened = (wrapper: VueWrapper) =>
  wrapper
    .findAll('table [data-slot="collapsible"]')
    .filter((d) => d.attributes('data-state') === 'open')
    .map((d) => d.get('[data-slot="collapsible-trigger"]').attributes('aria-label'))

afterEach(() => {
  vi.unstubAllGlobals()
  clear()
  document.body.innerHTML = ''
})

describe('a diff read again', () => {
  test('an_open_comment_form_stays_on_the_line_it_was_opened_on_when_lines_are_inserted_above', async () => {
    let body = BEFORE
    stubFetch(() => answer(body))
    const wrapper = mount(TicketChanges, {
      props: { ...SAMPLE, revision: 1 },
      attachTo: document.body,
    })
    await flushPromises()
    const second = wrapper
      .findAll('table [data-slot="collapsible"]')
      .find(
        (d) =>
          d.element
            .querySelector('[data-slot="collapsible-trigger"]')
            ?.getAttribute('aria-label') === 'Comment on src/app.ts line 2',
      )
    if (!second) throw new Error('the form for line 2 is missing')
    await second.get('[data-slot="collapsible-trigger"]').trigger('click')

    body = AFTER
    await wrapper.setProps({ revision: 2 })
    await flushPromises()

    expect(opened(wrapper)).toStrictEqual(['Comment on src/app.ts line 2'])
  })

  test('a_read_the_board_does_not_answer_keeps_the_rows_and_says_nothing', async () => {
    let fail = false
    stubFetch(() => {
      if (fail) return Promise.reject(new TypeError('Failed to fetch'))
      return answer(BEFORE)
    })
    const errors: unknown[] = []
    const wrapper = mount(TicketChanges, {
      props: { ...SAMPLE, revision: 1 },
      attachTo: document.body,
      global: { config: { errorHandler: (e: unknown) => errors.push(e) } },
    })
    await flushPromises()

    fail = true
    await wrapper.setProps({ revision: 2 })
    await flushPromises()

    expect(errors).toStrictEqual([])
    expect(notice.text).toBe('')
    expect(wrapper.text()).toContain('fresh()')
  })
})
