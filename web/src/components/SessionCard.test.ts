// @vitest-environment happy-dom
// CF-1204: a session waiting on the person, as a card with Open session.

import { variantOf } from '../test/button'
import { mount } from '@vue/test-utils'
import { describe, expect, test } from 'vitest'
import type { Session } from '../lib/sessions'
import SessionCard from './SessionCard.vue'

const waiting: Session = {
  session_id: 's-wait',
  cwd: '/work/api',
  repository: 'api',
  branch: 'feat/x',
  state: 'blocked',
  last_event_at: 1_790_000_000,
  stale: false,
  current_action: null,
  subagents: [],
  last_prompt: 'Allow the push?',
  turn_tool_calls: 0,
}

function card(first: boolean) {
  return mount(SessionCard, {
    props: { session: waiting, usage: undefined, now: 1_790_000_300, ticket: undefined, first },
    global: { stubs: { RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } } },
  })
}

describe('a waiting session card', () => {
  test('open_session_links_to_the_session_page', () => {
    const open = card(false).find('a[data-slot="button"]')

    expect(open.text()).toBe('Open session')
    expect(open.attributes('href')).toBe('/sessions/s-wait')
  })

  test('only_the_first_card_takes_the_primary_button', () => {
    expect(variantOf(card(true).get('a[data-slot="button"]'))).toBe('default')
    expect(card(false).find('a[data-slot="button"]').attributes('data-variant')).toBe('secondary')
  })

  test('it_reads_how_long_it_has_waited_and_what_it_asks', () => {
    const text = card(false).text()

    expect(text).toContain('waiting 5m')
    expect(text).toContain('Allow the push?')
    expect(text).toContain('api on feat/x')
  })

  // Beside what the session asks on a phone, the actions squeezed it to a few letters.
  test('on_a_phone_the_actions_take_their_own_line', () => {
    expect(card(false).get('[data-slot="item-actions"]').classes()).toContain('max-sm:basis-full')
  })
})
