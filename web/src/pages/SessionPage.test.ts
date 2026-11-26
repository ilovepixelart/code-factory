// @vitest-environment happy-dom
// CF-338: a session's timeline as docs/ui.md (The timeline) sets it, over a hand-built session.

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import type { Board } from '../lib/board'
import type { Entry, Session } from '../lib/sessions'
import { goldenBoard, memoryRouter, provideBoard } from '../test/board'
import { present } from '../test/present'
import SessionPage from './SessionPage.vue'
import {
  Cancel01Icon,
  ComputerTerminal01Icon,
  File01Icon,
  PencilEdit01Icon,
  Search01Icon,
} from '@hugeicons/core-free-icons'
import { draws } from '../test/icons'
import { testQueryClient } from '../test/unstubbed-fetch'

const POLL_MS = 3000

const session: Session = {
  session_id: 's-1',
  cwd: '/work/sample',
  repository: 'sample',
  branch: 'main',
  state: 'working',
  last_event_at: 1_790_000_500,
  stale: false,
  current_action: null,
  subagents: [],
  last_prompt: '',
  turn_tool_calls: 0,
}

let seq = 0
function entry(kind: string, detail = '', status = ''): Entry {
  seq += 1
  return {
    kind,
    seq,
    at: 1_790_000_000 + seq,
    agent_id: null,
    title: kind === 'tool' ? 'Bash' : kind,
    detail,
    duration_seconds: kind === 'tool' ? 1 : null,
    status,
  }
}

/** One turn: its prompt, one tool call with `status`, and its stop. */
function turn(prompt: string, status: string): Entry[] {
  return [entry('prompt', prompt), entry('tool', 'ls', status), entry('stop')]
}

interface Held {
  promise: Promise<Response>
  resolve: (answer: Response) => void
}

/** An answer the test gives when it chooses. */
function held(): Held {
  let resolve: (answer: Response) => void = () => undefined
  const promise = new Promise<Response>((done) => (resolve = done))
  return { promise, resolve }
}

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** The page over a server whose timeline answers whatever `answer.entries` holds when asked,
 * and whose calls answer `answer.calls[seq]`, or a 404 with its reason for a seq it lacks. */
async function page(answer: {
  entries: Entry[]
  total?: number
  earlier_prompts?: number
  session?: Session
  calls?: Record<number, unknown>
  usage?: Record<string, unknown>
  /** Holds the usage answer until the test answers it. */
  usageHeld?: Held
  /** Answers the timeline with this status and no body instead of the session. */
  timelineStatus?: number
  /** The board holding the session's ticket. */
  board?: Board
}) {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      const call = /\/calls\/(\d+)$/.exec(url)
      if (call) {
        const body = answer.calls?.[Number(call[1])]
        return Promise.resolve(
          body === undefined
            ? new Response(
                JSON.stringify({ detail: `no call ${String(call[1])} in session s-1` }),
                {
                  status: 404,
                  headers: { 'Content-Type': 'application/json' },
                },
              )
            : json(body),
        )
      }
      if (url === '/api/sessions/usage?session=s-1')
        return answer.usageHeld?.promise ?? Promise.resolve(json(answer.usage ?? {}))
      return Promise.resolve(
        url.includes('/timeline') && answer.timelineStatus
          ? new Response(JSON.stringify({ detail: 'the ledger is unreadable' }), {
              status: answer.timelineStatus,
              headers: { 'Content-Type': 'application/json' },
            })
          : url.includes('/timeline')
            ? json({
                session: answer.session ?? session,
                entries: answer.entries,
                total: answer.total ?? answer.entries.length,
                earlier_prompts: answer.earlier_prompts ?? 0,
              })
            : json({}),
      )
    }),
  )
  const router = memoryRouter([{ path: '/sessions/:id', component: SessionPage }])
  await router.push('/sessions/s-1')
  const view = mount(SessionPage, {
    attachTo: document.body,
    global: {
      plugins: [router],
      provide: provideBoard(answer.board ?? null),
      stubs: { teleport: true },
    },
  })
  await flushPromises()
  return view
}

/** The words beside the Timeline heading: they name the unit of each number. */
const timelineHint = () =>
  document
    .querySelector('#timeline-heading')
    ?.closest('[data-section]')
    ?.querySelector('[data-slot="section-description"]')?.textContent

const turns = () => [
  ...document.querySelectorAll<HTMLElement>('[data-slot="collapsible"][data-turn]'),
]
const TRIGGER = '[data-slot="collapsible-trigger"]'
const triggerOf = (turn: HTMLElement) =>
  present(turn.querySelector<HTMLElement>(TRIGGER), 'its trigger')
const isOpen = (turn: HTMLElement) => turn.dataset.state === 'open'
const headerOf = (turn: HTMLElement) =>
  [...triggerOf(turn).querySelectorAll(':scope > span > span')]
    .map((s) => s.textContent.trim())
    .join(' ')
const outcomeOf = (turn: HTMLElement) =>
  present(triggerOf(turn).querySelector('[data-slot="badge"]'), 'its outcome').textContent.trim()
const rowOf = (detail: string) =>
  present(
    [...document.querySelectorAll<HTMLLIElement>('[aria-label="Entries of turn 1"] li')].find(
      (li) => li.textContent.includes(detail),
    ),
    detail,
  )
const callsAsked = () =>
  vi
    .mocked(fetch)
    .mock.calls.map(([url]) => url)
    .filter((url): url is string => typeof url === 'string' && url.includes('/calls/'))

const timelinesAsked = () =>
  vi
    .mocked(fetch)
    .mock.calls.map(([url]) => url)
    .filter((url): url is string => typeof url === 'string' && url.includes('/timeline'))

/** Use the row's payload control and wait for its answer. */
async function toggle(row: HTMLLIElement) {
  present(row.querySelector<HTMLButtonElement>('button[aria-expanded]'), 'its control').click()
  await flushPromises()
}

beforeEach(() => {
  seq = 0
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

describe('the timeline', () => {
  test('the_latest_turn_and_any_turn_holding_a_failed_or_denied_call_are_open', async () => {
    const view = await page({
      entries: [
        ...turn('one', 'done'),
        ...turn('two', 'failed'),
        ...turn('three', 'denied'),
        ...turn('four', 'done'),
        ...turn('five', 'done'),
      ],
    })

    expect(turns().map(isOpen)).toEqual([false, true, true, false, true])
    view.unmount()
  })

  // CF-1227: a prompt sent while the turn before it still runs, and a turn ended later.
  test('a_turn_followed_by_a_later_turn_or_its_end_is_not_running', async () => {
    const view = await page({
      entries: [
        entry('prompt', 'one'),
        entry('tool', 'ls', 'done'),
        entry('prompt', 'two'),
        entry('tool', 'ls', 'done'),
        entry('stop'),
        entry('prompt', 'three'),
        entry('tool', 'ls', 'running'),
      ],
    })

    expect(turns().map(outcomeOf)).toEqual(['Done', 'Done', 'Running'])
    view.unmount()
  })

  test('a_turn_that_ended_reads_done_and_counts_its_failed_calls_apart', async () => {
    const view = await page({
      entries: [
        entry('prompt', 'one'),
        entry('tool', 'ls', 'failed'),
        entry('tool', 'ls', 'done'),
        entry('stop'),
      ],
    })
    const [only] = turns()

    expect(outcomeOf(present(only, 'the turn'))).toBe('Done')
    expect(headerOf(present(only, 'the turn'))).toContain('2 calls 1 failed')
    view.unmount()
  })

  test('a_turn_s_length_spans_its_first_to_its_last_event', async () => {
    const start = 1_790_000_000
    const view = await page({
      entries: [
        { ...entry('prompt', 'one'), at: start },
        { ...entry('stop'), at: start + 4.1 },
        { ...entry('tool', 'ls', 'done'), at: start + 60 },
        { ...entry('tool', 'ls', 'done'), at: start + 125.5 },
        { ...entry('prompt', 'two'), at: start + 200 },
      ],
    })
    const [first] = turns()

    expect(headerOf(present(first, 'the first turn'))).toContain('2m 5s')
    view.unmount()
  })

  test('a_turn_the_person_opened_stays_open_across_live_refreshes', async () => {
    const answer = { entries: [...turn('one', 'done'), ...turn('two', 'done')] }
    const view = await page(answer)
    const [first, latest] = turns()
    const opened = present(first, 'the first turn')
    const last = present(latest, 'the latest turn')
    for (const turn of [opened, last, last]) {
      triggerOf(turn).click()
      await flushPromises()
    }
    answer.entries = [...answer.entries, ...turn('three', 'done')]

    await vi.advanceTimersByTimeAsync(POLL_MS)
    await flushPromises()

    expect(turns()).toHaveLength(3)
    expect(turns().map(isOpen)).toEqual([true, true, true])
    view.unmount()
  })

  test('full_inputs_and_outputs_appear_only_on_request', async () => {
    const command = `echo ${'x'.repeat(245)}`
    const view = await page({
      entries: [entry('prompt', 'run it'), entry('tool', command, 'done'), entry('stop')],
    })
    const row = present(
      [...document.querySelectorAll('[aria-label="Entries of turn 1"] li')].find((li) =>
        li.textContent.includes('Bash'),
      ),
      'the Bash row',
    )
    const label = present(row.querySelector('[title]'), 'its label')

    expect(row.textContent).toContain(`Bash ${command.slice(0, 199)}…`)
    expect(row.textContent).not.toContain(command)
    expect(label.getAttribute('title')).toBe(command)
    view.unmount()
  })

  test('an_ended_session_s_last_event_does_not_count_on', async () => {
    const lastEvent = () =>
      [...document.querySelectorAll('dt')].find((d) => d.textContent.trim() === 'Last event')
        ?.nextElementSibling?.textContent
    const view = await page({
      entries: turn('one', 'done'),
      session: { ...session, state: 'ended' },
    })
    const first = lastEvent()

    await vi.advanceTimersByTimeAsync(POLL_MS)
    await flushPromises()

    expect(first).toContain('ended')
    expect(lastEvent()).toBe(first)
    view.unmount()
  })

  test('a_call_s_full_input_and_output_open_on_request', async () => {
    const view = await page({
      entries: [
        entry('prompt', 'run the tests'),
        entry('tool', 'cargo nextest run', 'done'),
        entry('tool', 'sleep 60', 'running'),
        entry('tool', 'gone', 'done'),
        entry('stop'),
      ],
      calls: {
        2: {
          tool: 'Bash',
          input: { command: 'cargo nextest run', description: 'Run the Rust tests' },
          output: { stdout: 'ok', exit_code: 0 },
        },
        3: { tool: 'Bash', input: { command: 'sleep 60' }, output: null },
      },
    })
    const finished = rowOf('cargo nextest run')
    const control = present(finished.querySelector('button[aria-expanded]'), 'its control')

    expect(callsAsked()).toEqual([])
    expect(document.querySelector('pre')).toBeNull()
    expect(control.textContent.trim()).toBe('Input and output')
    expect(control.getAttribute('aria-expanded')).toBe('false')
    expect(control.getAttribute('aria-label')).toBe('Input and output of call 2')
    expect(control.hasAttribute('aria-controls')).toBe(false)

    await toggle(finished)

    expect(callsAsked()).toEqual(['/api/sessions/s-1/calls/2'])
    expect(control.getAttribute('aria-expanded')).toBe('true')
    expect(control.textContent.trim()).toBe('Input and output')
    expect(control.getAttribute('aria-label')).toBe('Input and output of call 2')
    const panel = present(finished.querySelector('[role="region"]'), 'its panel')
    expect(panel.getAttribute('aria-label')).toBe('Input and output of call 2')
    expect(panel.id).not.toBe('')
    expect(control.getAttribute('aria-controls')).toBe(panel.id)
    expect([...finished.querySelectorAll('pre')].map((p) => p.textContent)).toEqual([
      '{\n  "command": "cargo nextest run",\n  "description": "Run the Rust tests"\n}',
      '{\n  "stdout": "ok",\n  "exit_code": 0\n}',
    ])
    expect(finished.textContent).toContain('Input')
    expect(finished.textContent).toContain('Output')

    await toggle(finished)

    expect(finished.querySelector('pre')).toBeNull()
    expect(control.getAttribute('aria-expanded')).toBe('false')

    await toggle(rowOf('sleep 60'))
    await toggle(rowOf('gone'))

    expect(rowOf('sleep 60').textContent).toContain('Not answered yet.')
    expect(rowOf('gone').textContent).toContain('no call 4 in session s-1')
    view.unmount()
  })

  test('an_unknown_session_says_so_in_its_heading_and_leads_back_to_sessions', async () => {
    const view = await page({ entries: [], timelineStatus: 404 })
    const back = present(document.querySelector('[data-slot="empty"] a'), 'the way back')

    expect(document.querySelector('h1')?.textContent.trim()).toBe('Session not found')
    expect([back.textContent.trim(), back.getAttribute('href')]).toEqual(['Sessions', '/'])
    view.unmount()
  })

  test('a_failed_first_read_names_the_session_instead_of_loading', async () => {
    const view = await page({ entries: [], timelineStatus: 500 })

    expect(document.querySelector('h1')?.textContent.trim()).toBe('Session s-1')
    view.unmount()
  })

  test('a_failed_timeline_read_says_so_and_reads_again_on_request', async () => {
    const view = await page({ entries: [], timelineStatus: 500 })

    const alert = present(document.querySelector('[role="alert"]'), 'its refusal')
    expect(alert.textContent).toContain('the ledger is unreadable')
    expect(document.body.textContent).not.toContain('Loading the session')
    const before = timelinesAsked().length

    present(alert.querySelector('button'), 'Read again').click()
    await flushPromises()

    expect(timelinesAsked().length).toBe(before + 1)
    view.unmount()
  })

  test('a_long_ticket_title_and_the_heading_carry_all_of_their_text_as_title', async () => {
    const title = 'A ticket title long enough that the page cuts it before its end '.repeat(3)
    const board = goldenBoard()
    const card = {
      ...present(board.columns.spec[0], 'a card'),
      title,
      sessions: [{ session_id: 's-1' }],
    }
    board.columns.spec = [card as (typeof board.columns.spec)[number]]
    const view = await page({ entries: [entry('prompt', 'go'), entry('stop')], board })

    const shown = present(
      [...document.querySelectorAll('a [data-slot="tooltip-trigger"]')].find(
        (s) => s.textContent === title,
      ),
      'the ticket title',
    )
    expect(shown.textContent).toBe(title)
    expect(document.querySelector('h1')?.getAttribute('title')).toBe('sample')
    view.unmount()
  })

  test('a_long_unbroken_prompt_word_breaks_inside_its_box', async () => {
    const view = await page({ entries: [entry('prompt', 'x'.repeat(90)), entry('stop')] })

    const prompt = present(document.querySelector(`${TRIGGER} [title^="xxxx"]`), 'the prompt')
    expect(prompt.classList.contains('wrap-anywhere')).toBe(true)
    view.unmount()
  })

  test('a_trimmed_field_shows_its_head_and_the_cut', async () => {
    const view = await page({
      entries: [
        entry('prompt', 'run the tests'),
        entry('tool', 'cargo build', 'done'),
        entry('stop'),
      ],
      calls: {
        2: {
          tool: 'Bash',
          input: { command: 'cargo build' },
          output: {
            stdout: { head: '   Compiling code-factory', _trimmed_chars: 18240 },
            exit_code: 0,
          },
        },
      },
    })
    const row = rowOf('cargo build')

    await toggle(row)

    expect(row.querySelectorAll('pre')[1]?.textContent).toBe(
      '{\n  "stdout": "   Compiling code-factory\u2026",\n  "exit_code": 0\n}',
    )
    expect(row.textContent).toContain('cut from 18,240 characters at capture')
    expect(row.textContent).not.toContain('_trimmed_chars')
    view.unmount()
  })
})

// CF-1384: a turn's entries as bars on the turn's own time axis, its gaps, failures and subagents.
describe('the timeline as a trace', () => {
  const T0 = 1_790_000_000
  /** An entry `offset` seconds into the turn; a tool call lasts `lasting` seconds. */
  function at(
    offset: number,
    kind: string,
    over: {
      title?: string
      detail?: string
      lasting?: number | null
      status?: string
      agent?: string
    } = {},
  ): Entry {
    seq += 1
    return {
      kind,
      seq,
      at: T0 + offset,
      agent_id: over.agent ?? null,
      title: over.title ?? (kind === 'tool' ? 'Bash' : kind),
      detail: over.detail ?? '',
      duration_seconds: kind === 'tool' ? (over.lasting ?? null) : null,
      status: over.status ?? '',
    }
  }
  const barOf = (row: HTMLLIElement) =>
    present(row.querySelector<HTMLElement>('[data-testid="bar"]'), 'its bar')
  const gaps = () =>
    [...document.querySelectorAll('li[data-testid="gap"]')].map((g) => g.textContent.trim())

  test('a_call_s_bar_sits_at_its_share_of_the_turn_s_axis', async () => {
    const view = await page({
      entries: [
        at(0, 'prompt', { detail: 'go' }),
        at(120, 'tool', { detail: 'five-minute', lasting: 300, status: 'done' }),
        at(600, 'stop'),
      ],
    })
    const bar = barOf(rowOf('five-minute'))

    expect(bar.style.left).toBe('20%')
    expect(bar.style.width).toBe('50%')
    view.unmount()
  })

  // The session works in /work/sample: a call on a file there names it from that folder.
  test('a_call_names_a_file_from_the_sessions_folder', async () => {
    const view = await page({
      entries: [
        at(0, 'prompt', { detail: 'go' }),
        at(1, 'tool', {
          title: 'Edit',
          detail: '/work/sample/src/rank.py',
          lasting: 1,
          status: 'done',
        }),
        at(2, 'stop'),
      ],
    })
    const call = present(rowOf('rank.py').querySelector('.font-mono.truncate'), 'the call')

    expect(call.textContent.trim()).toBe('Edit src/rank.py')
    view.unmount()
  })

  // On a phone the call shrank to its first letters beside its time, status and length, under a
  // rail indented as on a desktop: its icon and words lead the row and keep most of it, and the
  // rail indents less. The Timeline's own width decides it, not the window's: beside the sidebar
  // at 768 to 1279 px the seven columns left the call no width and ran out of the card.
  test('in_a_narrow_timeline_a_call_leads_its_row_under_a_narrower_rail', async () => {
    const view = await page({
      entries: [
        at(0, 'prompt', { detail: 'go' }),
        at(1, 'tool', { title: 'Read', detail: 'src/rank.py', lasting: 1, status: 'done' }),
        at(2, 'stop'),
      ],
    })
    const call = present(rowOf('rank.py').querySelector('.font-mono.truncate'), 'the call')
    const rail = present(document.querySelector('[aria-label="Entries of turn 1"]'), 'the rail')
    const timeline = present(document.querySelector('[aria-label="Timeline"]'), 'the timeline')

    const icon = present(call.previousElementSibling, 'its icon')
    expect(timeline.classList).toContain('@container')
    expect(
      [...icon.classList, ...call.classList].filter((c) => /^@?max-(md|4xl):/.test(c)),
    ).toEqual(['@max-4xl:order-first', '@max-4xl:order-first', '@max-4xl:min-w-[75%]'])
    expect([...rowOf('rank.py').classList].filter((c) => c.endsWith(':grid'))).toEqual([
      '@4xl:grid',
    ])
    expect([...rail.classList].filter((c) => /^(@?\w+:)?(ml|pl)-/.test(c))).toEqual([
      'ml-2',
      'pl-3',
      '@4xl:ml-8',
      '@4xl:pl-4',
    ])
    view.unmount()
  })

  test('a_call_with_no_length_still_draws_a_visible_bar', async () => {
    const view = await page({
      entries: [
        at(0, 'prompt', { detail: 'go' }),
        at(300, 'tool', { detail: 'instant', lasting: 0, status: 'done' }),
        at(600, 'stop'),
      ],
    })

    expect(Number.parseFloat(barOf(rowOf('instant')).style.width)).toBeGreaterThan(0)
    view.unmount()
  })

  test('a_gap_of_more_than_a_minute_is_marked_with_its_length', async () => {
    const view = await page({
      entries: [
        at(0, 'prompt', { detail: 'go' }),
        at(10, 'tool', { detail: 'before', lasting: 0, status: 'done' }),
        at(190, 'tool', { detail: 'after', lasting: 1, status: 'done' }),
        at(191, 'stop'),
      ],
    })

    expect(gaps()).toEqual(['3m idle'])
    view.unmount()
  })

  test('a_gap_of_a_minute_or_less_shows_no_marker', async () => {
    const view = await page({
      entries: [
        at(0, 'prompt', { detail: 'go' }),
        at(30, 'tool', { detail: 'thirty', lasting: 0, status: 'done' }),
        at(90, 'tool', { detail: 'sixty', lasting: 0, status: 'done' }),
        at(91, 'stop'),
      ],
    })

    expect(gaps()).toEqual([])
    view.unmount()
  })

  test('a_failed_call_marks_its_whole_row_with_the_error_token_and_says_so_besides_color', async () => {
    const view = await page({
      entries: [
        at(0, 'prompt', { detail: 'go' }),
        at(1, 'tool', { detail: 'broke', lasting: 1, status: 'failed' }),
        at(3, 'tool', { detail: 'fine', lasting: 1, status: 'done' }),
        at(5, 'stop'),
      ],
    })
    const failed = rowOf('broke')
    const passed = rowOf('fine')

    expect(failed.classList.contains('border-destructive')).toBe(true)
    expect([...failed.querySelectorAll('svg')].some((svg) => draws(svg, Cancel01Icon))).toBe(true)
    expect(failed.textContent).toContain('Failed')
    expect(passed.classList.contains('border-destructive')).toBe(false)
    expect([...passed.querySelectorAll('svg')].some((svg) => draws(svg, Cancel01Icon))).toBe(false)
    view.unmount()
  })

  test('a_denied_call_is_marked_like_a_failed_one', async () => {
    const view = await page({
      entries: [
        at(0, 'prompt', { detail: 'go' }),
        at(1, 'tool', { detail: 'no', status: 'denied' }),
      ],
    })

    expect(rowOf('no').classList.contains('border-destructive')).toBe(true)
    view.unmount()
  })

  test('a_subagent_s_entries_sit_under_one_row_naming_it_with_their_total_duration', async () => {
    const view = await page({
      session: {
        ...session,
        subagents: [
          {
            agent_id: 'a1',
            agent_type: 'Explore',
            running: false,
            stale: false,
            current_action: null,
          },
        ],
      },
      entries: [
        at(0, 'prompt', { detail: 'go' }),
        at(1, 'tool', { detail: 'main-call', lasting: 1, status: 'done' }),
        at(10, 'tool', { detail: 'sub-one', lasting: 30, status: 'done', agent: 'a1' }),
        at(50, 'tool', { detail: 'sub-two', lasting: 90, status: 'done', agent: 'a1' }),
        at(200, 'stop'),
      ],
    })
    const groups = [
      ...document.querySelectorAll<HTMLElement>('[data-slot="collapsible"][data-agent]'),
    ]
    const [group] = groups

    expect(groups).toHaveLength(1)
    const summary = present(
      group?.querySelector('[data-slot="collapsible-trigger"]'),
      'its summary',
    ).textContent
    expect(summary).toContain('Explore')
    expect(summary).toContain('2m 0s')
    expect(group?.textContent).toContain('sub-one')
    expect(group?.textContent).toContain('sub-two')
    expect(group?.textContent).not.toContain('main-call')
    view.unmount()
  })

  // A name on an element with no role is dropped (WAI-ARIA 1.2, aria-label is prohibited on the
  // generic role): the subagent's row is a group, so screen readers and its own name find it.
  test('a_subagent_s_row_is_a_group_named_for_the_subagent', async () => {
    const view = await page({
      session: {
        ...session,
        subagents: [
          {
            agent_id: 'a1',
            agent_type: 'Explore',
            running: false,
            stale: false,
            current_action: null,
          },
        ],
      },
      entries: [
        at(0, 'prompt', { detail: 'go' }),
        at(10, 'tool', { detail: 'sub-one', lasting: 30, status: 'done', agent: 'a1' }),
        at(200, 'stop'),
      ],
    })
    const group = present(document.querySelector('[data-agent="a1"]'), 'the subagent row')

    expect([group.getAttribute('role'), group.getAttribute('aria-label')]).toStrictEqual([
      'group',
      'Subagent Explore a1',
    ])
    view.unmount()
  })

  test('each_tool_kind_has_its_own_icon', async () => {
    const view = await page({
      entries: [
        at(0, 'prompt', { detail: 'go' }),
        at(1, 'tool', { title: 'Read', detail: 'a.rs', lasting: 1, status: 'done' }),
        at(2, 'tool', { title: 'Edit', detail: 'b.rs', lasting: 1, status: 'done' }),
        at(3, 'tool', { title: 'Bash', detail: 'ls', lasting: 1, status: 'done' }),
        at(4, 'tool', { title: 'Grep', detail: 'todo', lasting: 1, status: 'done' }),
      ],
    })
    const icon = (detail: string) => rowOf(detail).querySelector('svg')

    expect(draws(icon('a.rs'), File01Icon)).toBe(true)
    expect(draws(icon('b.rs'), PencilEdit01Icon)).toBe(true)
    expect(draws(icon('ls'), ComputerTerminal01Icon)).toBe(true)
    expect(draws(icon('todo'), Search01Icon)).toBe(true)
    expect(draws(icon('a.rs'), PencilEdit01Icon)).toBe(false)
    view.unmount()
  })
})

describe('the cost', () => {
  // CF-563: the page asks for its own session's usage, not every session's.
  test('the_page_reads_its_own_session_s_usage', async () => {
    const used = {
      input: 1,
      output: 2,
      cache_read: 0,
      cache_write: 0,
      cost: 1.25,
      reported_at: 1_790_000_000,
      cost_incomplete: false,
    }
    const view = await page({ entries: turn('one', 'done'), usage: { 's-1': used } })

    expect(view.text()).toContain('$1.25 reported at')
  })

  // CF-1088-R1
  test('shows_the_timeline_before_the_usage_answers', async () => {
    const usageHeld = held()
    const view = await page({ entries: turn('one', 'done'), usageHeld })

    expect(view.text()).not.toContain('Loading the session')
    expect(turns()).toHaveLength(1)
    expect(view.text()).toContain('cost not reported yet')
    usageHeld.resolve(json({}))
    await flushPromises()
    view.unmount()
  })

  // CF-1088-R2
  test('the_usage_fills_in_when_it_answers', async () => {
    const usageHeld = held()
    const view = await page({ entries: turn('one', 'done'), usageHeld })
    usageHeld.resolve(
      json({
        's-1': {
          input: 1,
          output: 2,
          cache_read: 0,
          cache_write: 0,
          cost: 2.5,
          reported_at: 1_790_000_000,
          cost_incomplete: false,
        },
      }),
    )
    await flushPromises()

    expect(view.text()).toContain('$2.50 reported at')
    view.unmount()
  })
})

describe('a long session', () => {
  // CF-1066-R3
  test('shows_the_latest_entries_and_asks_for_earlier_ones', async () => {
    const view = await page({
      entries: [...turn('one', 'done'), ...turn('two', 'done')],
      total: 1200,
    })

    expect(timelinesAsked()).toEqual(['/api/sessions/s-1/timeline?last=500'])
    expect(timelineHint()).toBe('2 turns, latest 6 of 1,200 entries')
    present(
      [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === 'Show earlier'),
      'Show earlier',
    ).click()
    await flushPromises()

    expect(timelinesAsked().at(-1)).toBe('/api/sessions/s-1/timeline?last=1000')
    view.unmount()
  })

  // Showing earlier entries replaces the session's timeline in the cache: the shorter reads before
  // it are not kept beside it.
  test('a_session_keeps_one_timeline_however_far_back_it_is_shown', async () => {
    const view = await page({
      entries: [...turn('one', 'done'), ...turn('two', 'done')],
      total: 2000,
    })
    const earlier = () => {
      present(
        [...document.querySelectorAll('button')].find(
          (b) => b.textContent.trim() === 'Show earlier',
        ),
        'Show earlier',
      ).click()
    }
    earlier()
    await flushPromises()
    earlier()
    await flushPromises()
    const kept = testQueryClient()
      .getQueryCache()
      .findAll({ queryKey: ['sessions', 'timeline', 's-1'] }).length

    expect([timelinesAsked().at(-1), kept]).toEqual(['/api/sessions/s-1/timeline?last=1500', 1])
    view.unmount()
  })

  // CF-1066-R3
  test('a_session_shown_whole_has_no_show_earlier', async () => {
    const view = await page({ entries: turn('one', 'done') })

    expect(timelineHint()).toBe('1 turn, 3 entries')
    expect(
      [...document.querySelectorAll('button')].some((b) => b.textContent.trim() === 'Show earlier'),
    ).toBe(false)
    view.unmount()
  })

  // CF-1066-R3
  test('numbers_turns_after_the_prompts_not_shown', async () => {
    const view = await page({
      entries: [entry('tool', 'ls', 'done'), entry('stop'), ...turn('next', 'done')],
      total: 900,
      earlier_prompts: 4,
    })

    const titles = turns().map((t) =>
      [...t.querySelectorAll(`${TRIGGER} span span`)]
        .map((part) => part.textContent.trim())
        .join(' '),
    )
    expect(titles[0]).toContain('Turn 4 continued')
    expect(titles[1]).toContain('Turn 5 next')
    view.unmount()
  })
  // The Sessions list calls a session past its quiet threshold Stale: its page uses the same word
  // for its state, its open turn and its open call, and says nothing runs.
  test('a_stale_session_reads_stale_and_nothing_in_it_reads_running', async () => {
    const view = await page({
      session: { ...session, stale: true },
      entries: [entry('prompt', 'one'), entry('tool', 'sleep', 'running')],
    })
    const facts = present(
      document.querySelector('#session-facts-heading')?.closest('[data-section]'),
      'the facts',
    )
    const call = present(rowOf('sleep').querySelector('[data-slot="badge"]'), 'its status')

    expect(facts.querySelector('[data-slot="badge"]')?.textContent.trim()).toBe('Stale')
    expect(facts.textContent).not.toContain('Working')
    expect([...turns().map(outcomeOf), call.textContent.trim()]).toEqual(['Stale', 'Stale'])
    view.unmount()
  })

  // CF-1281: a call of a stopped or stale subagent is not drawn as running.
  test('an_open_call_of_a_stopped_or_stale_subagent_does_not_read_running', async () => {
    const call = (detail: string, agent: string): Entry => ({
      ...entry('tool', detail, 'running'),
      agent_id: agent,
    })
    const agent = (id: string, over: object) => ({
      agent_id: id,
      agent_type: 'worker',
      running: true,
      stale: false,
      current_action: null,
      ...over,
    })
    const view = await page({
      session: {
        ...session,
        subagents: [
          agent('gone', { running: false }),
          agent('late', { stale: true }),
          agent('busy', {}),
        ],
      },
      entries: [
        entry('prompt', 'one'),
        call('call-gone', 'gone'),
        call('call-late', 'late'),
        call('call-busy', 'busy'),
      ],
    })

    const badge = (detail: string) =>
      present(rowOf(detail).querySelector('[data-slot="badge"]'), detail).textContent.trim()
    expect([badge('call-gone'), badge('call-late'), badge('call-busy')]).toEqual([
      'Interrupted',
      'Stale',
      'Running',
    ])
    view.unmount()
  })
})
