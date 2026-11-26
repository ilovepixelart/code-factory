// @vitest-environment happy-dom
// CF-338: a session row's states as docs/ui.md (The board) sets them.

import { mount, RouterLinkStub } from '@vue/test-utils'
import { describe, expect, test } from 'vitest'
import type { Card } from '../lib/board'
import type { Session } from '../lib/sessions'
import SessionRow from './SessionRow.vue'
import { TONE_VARIANTS } from '../lib/status_tone'

function session(state: string, stale: boolean): Session {
  return {
    session_id: `s-${state}`,
    cwd: '/work/sample',
    repository: 'sample',
    branch: 'main',
    state,
    last_event_at: 1_790_000_000,
    stale,
    current_action: null,
    subagents: [],
    last_prompt: '',
    turn_tool_calls: 0,
  }
}

function row(shown: Session, now = 1_790_003_600): string {
  return mount(SessionRow, {
    props: { session: shown, usage: undefined, now, ticket: undefined },
    global: { stubs: { RouterLink: true } },
  }).text()
}

describe('a session row', () => {
  test('stale_is_its_own_state_distinct_from_idle', () => {
    const quiet = row(session('working', true))
    const idle = row(session('idle', false))

    expect(quiet).toContain('Stale')
    expect(quiet).not.toContain('Idle')
    expect(idle).toContain('Idle')
    expect(idle).not.toContain('Stale')
  })

  test('an_ended_session_s_age_freezes', () => {
    const first = row(session('ended', false), 1_790_000_100)
    const later = row(session('ended', false), 1_790_000_103)

    expect(later).toBe(first)
    expect(first).not.toContain(' ago')
  })
})

describe('a stale session (CF-1067)', () => {
  const chip = (shown: Session) =>
    mount(SessionRow, {
      props: { session: shown, usage: undefined, now: 1_790_003_600, ticket: undefined },
      global: { stubs: { RouterLink: true } },
    }).find('[data-slot="badge"]')

  // CF-1067-R1: a working session past the threshold reads Stale in the warning tone, once.
  test('a_stale_session_reads_stale', () => {
    const shown = chip(session('working', true))
    const text = row(session('working', true))

    expect(shown.text()).toBe('Stale')
    expect(shown.attributes('data-variant')).toBe(TONE_VARIANTS.warning)
    expect(text).not.toContain('Working')
    expect(text).not.toContain('· stale')
  })

  // CF-1067-R2: a working session within the threshold still reads Working.
  test('a_working_session_reads_working', () => {
    expect(chip(session('working', false)).text()).toBe('Working')
  })
})

// CF-1204: a compact row, the tool line and subagents on expand, the place when no ticket owns it.
describe('a compact session row (CF-1204)', () => {
  const busy: Session = {
    ...session('working', false),
    current_action: { tool: 'Bash', summary: 'cargo test', started_at: 1_790_000_000 },
    subagents: [
      { agent_id: 'a-1', agent_type: 'worker', running: true, stale: false, current_action: null },
    ],
  }
  const mounted = (shown: Session) =>
    mount(SessionRow, {
      props: { session: shown, usage: undefined, now: 1_790_000_060, ticket: undefined },
      global: { stubs: { RouterLink: true } },
    })

  test('the_tool_line_and_subagents_sit_inside_an_expander', () => {
    const wrapper = mounted(busy)
    const details = wrapper.find('[data-slot="collapsible"]')

    expect(details.exists()).toBe(true)
    expect(details.attributes('data-state')).toBe('closed')
    expect(details.text()).toContain('cargo test')
    expect(details.text()).toContain('worker')
    const line = wrapper.get('[data-slot="item-description"]').element
    expect(line.textContent).toContain('Bash cargo test')
    expect(line.compareDocumentPosition(details.element) & Node.DOCUMENT_POSITION_FOLLOWING).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    )
  })

  // CF-1281: a stopped subagent is counted finished and draws no tool call; a stale one reads stale.
  test('a_stopped_subagent_draws_no_tool_call_and_a_stale_one_reads_stale', () => {
    const call = { tool: 'Bash', summary: 'pkill node', started_at: 1_790_000_000 }
    const agent = (id: string, over: object) => ({
      agent_id: id,
      agent_type: 'worker',
      running: true,
      stale: false,
      current_action: null,
      ...over,
    })
    const wrapper = mounted({
      ...session('working', false),
      subagents: [
        agent('done-1', { running: false, current_action: call }),
        agent('late-2', { stale: true, current_action: call }),
        agent('busy-3', { current_action: { ...call, summary: 'cargo test' } }),
      ],
    })
    const text = wrapper.find('[data-slot="collapsible"]').text()

    expect(text).not.toContain('pkill')
    expect(text).toContain('1 subagent finished')
    expect(text).toContain('worker late-2 · stale')
    expect(text).not.toContain('late-2 · running')
    expect(text).toContain('worker busy-3 · running · Bash cargo test')
  })

  // The short id under the title is the link to the session, and its text says so.
  test('the_session_link_says_it_is_the_session', () => {
    const text = mount(SessionRow, {
      props: {
        session: session('idle', false),
        usage: undefined,
        now: 1_790_003_600,
        ticket: undefined,
      },
      global: { stubs: { RouterLink: RouterLinkStub } },
    }).text()

    expect(text).toContain('session s-idle')
  })

  test('a_session_with_nothing_to_expand_has_no_expander', () => {
    expect(mounted(session('idle', false)).find('details').exists()).toBe(false)
  })

  test('a_session_without_a_ticket_names_its_repository_and_branch', () => {
    expect(mounted(session('idle', false)).text()).toContain('sample on main')
  })

  test('under_its_repository_a_row_does_not_name_the_repository_again', () => {
    const wrapper = mount(SessionRow, {
      props: {
        session: session('idle', false),
        usage: undefined,
        now: 1_790_000_060,
        ticket: undefined,
        grouped: true,
      },
      global: { stubs: { RouterLink: true } },
    })

    expect(wrapper.text()).toContain('main')
    expect(wrapper.text()).not.toContain('sample')
  })

  // CF-1217: the ticket's pull request label shows on its session's row, none without a pull.
  test('a_row_shows_the_state_of_its_tickets_pull_request', () => {
    const withPull = (pull: Card['pull']) =>
      mount(SessionRow, {
        props: {
          session: session('idle', false),
          usage: undefined,
          now: 1_790_000_060,
          ticket: { id: 'CF-1', title: 'T', repository: 'sample', pull, check: null } as Card,
        },
        global: { stubs: { RouterLink: true } },
      })
    const open = { state: 'open', ci: 'passed', head: 'h', url: 'u/1', at: '1', conflict: true }

    const conflicted = withPull(open).find('[data-pull-state]')
    expect(conflicted.text()).toBe('Conflict')
    expect(conflicted.attributes('data-variant')).toBe(TONE_VARIANTS.warning)
    expect(withPull(null).find('[data-pull-state]').exists()).toBe(false)
  })

  // Beside the title on a phone, the cost and age squeezed it to a few letters and were drawn over
  // the session link.
  test('on_a_phone_the_cost_and_age_take_their_own_line', () => {
    const actions = mounted(session('idle', false)).get('[data-slot="item-actions"]')

    expect(actions.classes()).toContain('max-sm:basis-full')
  })
})
