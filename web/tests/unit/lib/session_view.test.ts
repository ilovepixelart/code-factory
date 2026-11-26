// CF-1204: how the Sessions page reads a session, worked by hand from the ticket.

import { describe, expect, test } from 'vitest'
import { doing, entryStatus, filterOf, placeOf, rowLine, stateOf } from '@/lib/session_view'
import type { Entry, Session } from '@/lib/sessions'

function session(over: Partial<Session>): Session {
  return {
    session_id: 's-1',
    cwd: '/work/api',
    repository: 'api',
    branch: 'main',
    state: 'working',
    last_event_at: 0,
    stale: false,
    current_action: null,
    subagents: [],
    last_prompt: '',
    turn_tool_calls: 0,
    ...over,
  }
}

describe('a session as the page reads it', () => {
  test('a_blocked_session_counts_as_waiting', () => {
    expect(stateOf(session({ state: 'blocked' }))).toBe('waiting')
  })

  test('a_quiet_working_session_counts_as_stale_not_working', () => {
    expect(stateOf(session({ state: 'working', stale: true }))).toBe('stale')
    expect(stateOf(session({ state: 'working' }))).toBe('working')
    expect(stateOf(session({ state: 'idle' }))).toBe('idle')
  })

  test('an_ended_session_counts_under_no_chip', () => {
    expect(stateOf(session({ state: 'ended' }))).toBeNull()
  })

  test('only_the_four_states_filter', () => {
    expect(filterOf('idle')).toBe('idle')
    expect(filterOf('ended')).toBeNull()
    expect(filterOf(undefined)).toBeNull()
  })

  test('a_session_without_a_ticket_reads_repository_and_branch', () => {
    expect(placeOf(session({}))).toBe('api on main')
    expect(placeOf(session({ branch: '' }))).toBe('api')
    expect(placeOf(session({ repository: '', branch: '' }))).toBe('unknown repository')
  })

  test('doing_is_the_open_tool_call_else_the_last_prompt', () => {
    const action = { tool: 'Bash', summary: 'cargo test', started_at: 1 }
    expect(doing(session({ current_action: action, last_prompt: 'fix it' }))).toBe(
      'Bash cargo test',
    )
    expect(doing(session({ last_prompt: 'fix it' }))).toBe('fix it')
    expect(doing(session({}))).toBe('')
  })
})

// CF-1281: an open call of a subagent that is stale or no longer running is not drawn as running.
describe('an entry of a subagent (CF-1281)', () => {
  const call = (agent: string | null, status: string): Entry => ({
    kind: 'tool',
    seq: 1,
    at: 0,
    agent_id: agent,
    title: 'Bash',
    detail: 'ls',
    duration_seconds: null,
    status,
  })
  const agent = (over: object) => ({
    agent_id: 'a',
    agent_type: 'worker',
    running: true,
    stale: false,
    current_action: null,
    ...over,
  })

  test('a_running_call_of_a_stale_subagent_reads_stale', () => {
    const shown = session({ subagents: [agent({ stale: true })] })

    expect(entryStatus(call('a', 'running'), shown)).toBe('stale')
  })

  test('a_running_call_of_a_subagent_that_is_not_running_reads_interrupted', () => {
    const shown = session({ subagents: [agent({ running: false })] })

    expect(entryStatus(call('a', 'running'), shown)).toBe('interrupted')
  })

  test('a_call_of_a_working_subagent_or_the_session_or_a_finished_call_keeps_its_status', () => {
    const shown = session({ subagents: [agent({})] })

    expect(entryStatus(call('a', 'running'), shown)).toBe('running')
    expect(entryStatus(call(null, 'running'), shown)).toBe('running')
    expect(
      entryStatus(call('a', 'done'), session({ subagents: [agent({ running: false })] })),
    ).toBe('done')
  })

  test('a_row_says_the_servers_line_else_the_prompt_as_before', () => {
    expect(rowLine(session({ doing: 'plan 3/7: run it', last_prompt: 'fix it' }), 500)).toBe(
      'plan 3/7: run it',
    )
    expect(rowLine(session({ doing: '', last_prompt: 'fix it' }), 500)).toBe('fix it')
    expect(rowLine(session({ last_prompt: 'fix it' }), 500)).toBe('fix it')
  })

  test('a_last_call_line_says_how_long_ago_it_began', () => {
    const line = session({ doing: 'last call: Read a.rs', doing_since: 100 })
    expect(rowLine(line, 220)).toBe('last call: Read a.rs, 2m ago')
    expect(rowLine(line, 120)).toBe('last call: Read a.rs, 20s ago')
  })

  // A path inside the session's own folder is shown from that folder, not from the disk's root;
  // a path elsewhere, and a folder that is the root, are left as they are.
  test('a_row_shows_paths_from_the_sessions_folder', () => {
    const at = (cwd: string, doing: string) => rowLine(session({ cwd, doing }), 0)

    expect(at('/home/a/repo', 'last call: Edit /home/a/repo/src/rank.py')).toBe(
      'last call: Edit src/rank.py',
    )
    expect(at('/home/a/repo', 'last call: Read /home/a/repo-old/x.py')).toBe(
      'last call: Read /home/a/repo-old/x.py',
    )
    expect(at('/', 'last call: Read /etc/hosts')).toBe('last call: Read /etc/hosts')
    expect(at('', 'last call: Read /etc/hosts')).toBe('last call: Read /etc/hosts')
    expect(
      rowLine(
        session({ cwd: '/w', current_action: { tool: 'Edit', summary: '/w/a.ts', started_at: 0 } }),
        0,
      ),
    ).toBe('Edit a.ts')
  })
})
