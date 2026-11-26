// CF-1184: a card says which session subagent is at work on it, what it is doing and for how
// long, and links to its session.

import { mount } from '@vue/test-utils'
import { afterEach, expect, test, vi } from 'vitest'
import type { Card } from '@/lib/board'
import { goldenBoard, memoryRouter } from '../../support/board'
import { present } from '../../support/present'
import TicketCardBadges from '@/components/TicketCardBadges.vue'

const SINCE = 1_790_000_000

afterEach(() => {
  vi.useRealTimers()
})

function badges(subagents: Card['subagents']) {
  const golden = present(goldenBoard().columns.spec[0], 'a card')
  const card: Card = {
    ...golden,
    open_questions: 0,
    runs: [],
    sessions: [],
    halted: '',
    limited_until: null,
    subagents,
  }
  return mount(TicketCardBadges, { props: { card }, global: { plugins: [memoryRouter()] } })
}

// CF-1184-R3
test('a_subagent_badge_says_who_what_and_how_long', () => {
  vi.useFakeTimers()
  vi.setSystemTime((SINCE + 12 * 60) * 1000)
  const view = badges([
    {
      ticket: 'CF-1',
      session_id: 's-coordinator',
      agent_id: 'a1b2c3d4',
      name: 'ticket-worker a1b2',
      kind: 'session',
      doing: 'Bash cargo test --workspace',
      since: SINCE,
      last_event_at: SINCE + 600,
    },
  ])

  const link = view.find('a[href="/sessions/s-coordinator"]')
  expect(link.exists()).toBe(true)
  expect(link.get('[data-slot="trace-title"]').text()).toBe(
    'Running ticket-worker a1b2: Bash cargo test --workspace',
  )
  expect(link.get('[data-slot="trace-description"]').text()).toBe('12m')
  expect(link.get('[data-slot="trace-line"]').attributes('data-status')).toBe('running')
  expect(link.attributes('title')).toBe('ticket-worker a1b2: Bash cargo test --workspace, for 12m')
})

// CF-1184-R3: no subagent, no badge row.
test('a_card_with_no_subagent_shows_no_subagent_badge', () => {
  expect(badges([]).html()).toBe('<!--v-if-->')
})
