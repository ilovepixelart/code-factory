// @vitest-environment happy-dom
// CF-400-R4: the ticket page shows what the ticket proved and what it did not.

import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import TicketSummary from './TicketSummary.vue'

test('a_ticket_page_shows_its_evidence_summary', () => {
  const view = mount(TicketSummary, {
    props: {
      summary: {
        gate: { held: true, commit: 'c0ffee1234', tree: 't1' },
        verdict: 'pass',
        capture: { tree: 't1', approved: false },
        not_proven: ['CF-1-R2: Given the page, then it reads well'],
      },
    },
  })

  const items = view.findAll('li').map((li) => li.text())
  expect(items).toStrictEqual([
    'Gate passed on c0ffee1, tree t1',
    'Review verdict: pass',
    'Capture not approved, tree t1',
    'CF-1-R2: Given the page, then it reads well',
  ])
  expect(view.text()).toContain('Not proven, checked by review only')
})
