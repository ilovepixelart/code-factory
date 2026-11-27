import { flushPromises, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { ESTIMATE_NOTE } from '@/lib/format'
import { BASE, form, view } from '../../../support/ticketForm'

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

// CF-846-R8: in Spec, the agent's next step names the requirements document, where the
// requirements and their tests now live.
test('the_spec_step_names_the_requirements_document', async () => {
  const { page } = await form({ ...(view as object), current_stage: 'spec', runs: [] })

  const next = page.findAll('p').find((p) => p.text().startsWith('Next:'))

  expect(next?.text()).toBe('Next: the requirements, each with its named check, requirements.md')
  page.unmount()
})

// CF-651-R3: hand-worked, $0.75 of review in $4.00 (18.75%, shown 19%), 15 turns and 5,000
// cache reads read "review $0.75 (19%) · 15 turns · 5k cache reads"; a part no run reported is
// left out.
test('the_ticket_shows_what_its_cost_is_made_of', async () => {
  const shown = (cost: object) => ({ ...(view as object), spent: 4, cost })
  // One ticket at a time: two forms of the same ticket share its one read.
  const breakdown = async (cost: object) => {
    const { page } = await form(shown(cost))
    const text = page.find('[aria-label="Cost breakdown"]')
    const said = text.exists() && text.text()
    page.unmount()
    return said
  }

  expect([
    await breakdown({ total: 4, review: 0.75, cache_read: 5000, turns: 15 }),
    await breakdown({ total: 4, review: null, cache_read: null, turns: 3 }),
  ]).toEqual(['review $0.75 (19%) · 15 turns · 5k cache reads', '3 turns'])
})

// CF-1216: the section's spend is led by `~` when it holds the board's estimate, and a
// review that cost nothing is left out of the parts.
test('the_tickets_estimated_spend_is_marked', async () => {
  const parts = { total: 0, review: 0, cache_read: null, turns: 4 }
  const shown = async (fields: object) => {
    const { page } = await form({ ...(view as object), cost: parts, ...fields })
    const chip = page.find('#agent-heading span.tabular-nums')
    const breakdown = page.find('[aria-label="Cost breakdown"]')
    const seen = [
      chip.exists() ? chip.text() : null,
      chip.exists() ? chip.attributes('title') : null,
      breakdown.exists() ? breakdown.text() : null,
    ]
    page.unmount()
    return seen
  }

  expect([
    await shown({ spent: 3.25, spent_estimated: true, budget: 2.5 }),
    await shown({ spent: 3.25, spent_estimated: true, budget: null }),
    await shown({ spent: 3.25, budget: null }),
    await shown({ spent: 0, spent_estimated: true, budget: null }),
  ]).toEqual([
    ['~$3.25 of $2.50', `Agent spend against the ticket's budget; ${ESTIMATE_NOTE}`, '4 turns'],
    ['~$3.25', `Agent spend on this ticket; ${ESTIMATE_NOTE}`, '4 turns'],
    ['$3.25', 'Agent spend on this ticket', '4 turns'],
    [null, null, '4 turns'],
  ])
})

// CF-671-R5: one line for the repository's monthly budget: the day it runs out in the warning
// colour, a lasting month in the faint one, a spent budget in the error colour, none without one.
test('the_agent_section_says_when_the_month_budget_runs_out', async () => {
  const shown = async (month: object | null) => {
    const { page } = await form({ ...(view as object), month_budget: month })
    const line = page.find('[aria-label="Month budget"]')
    const seen = line.exists()
      ? [
          line.text(),
          line.classes('text-foreground')
            ? 'warning'
            : line.classes('text-destructive')
              ? 'error'
              : line.classes('text-muted-foreground')
                ? 'text-muted-foreground'
                : '',
        ]
      : null
    page.unmount()
    return seen
  }
  const month = { month: '2026-09', budget: 12, runs_out: null, reached: false }

  expect([
    await shown({ ...month, spent: 10, runs_out: '2026-09-25' }),
    await shown({ ...month, spent: 0 }),
    await shown({ ...month, spent: 12.4, reached: true }),
    await shown(null),
  ]).toEqual([
    ['Month budget: $10.00 of $12.00, runs out 25 Sep at this pace', 'warning'],
    ['Month budget: $0.00 of $12.00, lasts the month at this pace', 'text-muted-foreground'],
    ['Month budget: $12.40 of $12.00, reached', 'error'],
    null,
  ])
})

const running = (progress?: object, stage = 'build') => ({
  ...(view as object),
  runs: [{ id: 'r1', stage, iteration: 1, loop: false, started_at: 0, progress }],
})

test('a split without reported progress still shows its status and stop control', async () => {
  const { page } = await form(running(undefined, 'split'))

  expect(page.text()).toContain('Iteration 1 on Split')
  expect(page.text()).toContain('tool calls not known')
  expect(page.findAll('button').map((button) => button.text())).toContain('Stop agent')
  page.unmount()
})

// CF-1036-R12: hand-worked from the measured CF-918 run: 59 calls less 13 read and 0 changed is
// 46 other, 2,200,661 tokens read 2.2M, and a log that grew 120 seconds ago reads 2m ago.
test('the_agent_panel_shows_a_running_runs_progress', async () => {
  const { page } = await form(
    running({
      tool_calls: 59,
      reads: 13,
      changes: 0,
      files: { count: 12, names: ['a.rs', 'b.rs'] },
      tokens: 2_200_661,
      last_activity: Date.now() / 1000 - 120,
    }),
  )

  const lines = page.findAll('[aria-label="Run progress"] p')

  expect(lines.map((l) => l.text())).toEqual([
    '59 tool calls: 13 read, 0 changed files, 46 other',
    '12 files changed in its worktree · 2.2M tokens so far',
    'last activity 2m ago',
    'a.rs, b.rs and 10 more',
  ])
  page.unmount()
})

// CF-1036-R13: every number null reads `not known`, and none of them reads 0.
test('the_agent_panel_says_not_known_for_what_the_log_cannot_tell', async () => {
  const { page } = await form(
    running({
      tool_calls: null,
      reads: null,
      changes: null,
      files: null,
      tokens: null,
      last_activity: null,
    }),
  )

  const lines = page.findAll('[aria-label="Run progress"] p')

  expect(lines.map((l) => l.text())).toEqual([
    'tool calls not known',
    'files changed not known · tokens not known',
    'last activity not known',
  ])
  page.unmount()
})

test('the_agent_panel_uses_the_singular_for_one_call_and_one_changed_file', async () => {
  const { page } = await form(
    running({
      tool_calls: 2,
      reads: 0,
      changes: 1,
      files: { count: 1, names: ['a.rs'] },
      tokens: 5,
      last_activity: Date.now() / 1000 - 60,
    }),
  )

  const lines = page.findAll('[aria-label="Run progress"] p')

  expect(lines.map((l) => l.text())).toEqual([
    '2 tool calls: 0 read, 1 changed file, 1 other',
    '1 file changed in its worktree · 5 tokens so far',
    'last activity 1m ago',
    'a.rs',
  ])
  page.unmount()
})

// CF-1036-R14: with a run the ticket is read again each 5 seconds; with none it is not.
test('the_agent_panel_reads_progress_again_while_a_run_is_active', async () => {
  const reads = () => vi.mocked(fetch).mock.calls.filter(([url]) => url === BASE).length
  const known = {
    tool_calls: 0,
    reads: 0,
    changes: 0,
    files: { count: 0, names: [] },
    tokens: 0,
    last_activity: 0,
  }
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] })
  try {
    const active = await form(running(known))
    const atFirst = reads()
    await vi.advanceTimersByTimeAsync(5000)
    const afterOne = reads()
    await vi.advanceTimersByTimeAsync(5000)
    const afterTwo = reads()
    active.page.unmount()

    const idle = await form({ ...(view as object), runs: [] })
    const idleFirst = reads()
    await vi.advanceTimersByTimeAsync(10000)
    const idleAfter = reads()
    idle.page.unmount()

    expect([afterOne - atFirst, afterTwo - afterOne, idleAfter - idleFirst]).toEqual([1, 1, 0])
  } finally {
    vi.useRealTimers()
  }
})

// A ticket left open in a hidden tab costs no requests: its run's progress is read again as the
// tab shows.
test('the_agent_panel_stops_reading_progress_while_the_tab_is_hidden', async () => {
  const reads = () => vi.mocked(fetch).mock.calls.filter(([url]) => url === BASE).length
  const seen = (state: DocumentVisibilityState): void => {
    Object.defineProperty(document, 'visibilityState', { value: state, configurable: true })
    document.dispatchEvent(new Event('visibilitychange', { bubbles: true }))
  }
  const known = {
    tool_calls: 0,
    reads: 0,
    changes: 0,
    files: { count: 0, names: [] },
    tokens: 0,
    last_activity: 0,
  }
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] })
  try {
    const active = await form(running(known))
    seen('hidden')
    const before = reads()
    await vi.advanceTimersByTimeAsync(15000)
    const hidden = reads() - before
    seen('visible')
    await vi.advanceTimersByTimeAsync(0)
    const back = reads() - before - hidden
    active.page.unmount()

    expect({ hidden, back }).toEqual({ hidden: 0, back: 1 })
  } finally {
    seen('visible')
    vi.useRealTimers()
  }
})

// Start agent is not offered while the ticket is worked on: a named holder or a session subagent
// at work holds it, as a run of its own does.
test('the_agent_section_offers_no_start_while_the_ticket_is_worked_on', async () => {
  const golden = view as { card?: Record<string, unknown> | null }
  const building = {
    ...(view as object),
    current_stage: 'build',
    work_done: false,
    runs: [],
    questions: [],
    card: { ...(golden.card ?? {}), holder: undefined, queue: undefined },
    subagents: [],
  }
  const starts = async (extra: object) => {
    const { page } = await form({ ...building, ...extra })
    const found = page.findAll('button').filter((b) => b.text() === 'Start agent').length
    page.unmount()
    return found
  }
  const subagent = {
    agent_id: 'a1',
    session_id: 's1',
    name: 'builder',
    kind: 'session',
    ticket: 'CF-1',
    last_event_at: 0,
    doing: 'Edit',
    since: 0,
  }

  expect([
    await starts({}),
    await starts({ card: { ...building.card, holder: 'builder' } }),
    await starts({ subagents: [subagent] }),
  ]).toEqual([1, 0, 0])
})

// The permissions choice is a horizontal ToggleGroup: its first and last items take the group's
// rounded ends from the orientation it states.
test('the_permissions_choice_is_a_horizontal_toggle_group', async () => {
  const { page } = await form({ ...(view as object), current_stage: 'build', runs: [] })
  const group = page.find('[role="group"][aria-label="Permissions"]')

  expect([group.attributes('data-slot'), group.attributes('data-orientation')]).toEqual([
    'toggle-group',
    'horizontal',
  ])
  page.unmount()
})

// The audit: the start options carried no explanation. They fold under Options, whose trigger
// names the choice, and each control says in one line what it does.
describe('the start options', () => {
  const build = { ...(view as object), current_stage: 'build', runs: [] }
  const help = (page: VueWrapper, selector: string): string => {
    const id = page.get(selector).attributes('aria-describedby') ?? ''
    return document.getElementById(id)?.textContent.trim() ?? ''
  }

  test('fold_under_options_whose_trigger_names_the_choice', async () => {
    const { page } = await form(build)
    const fold = page.get('[aria-label="Start options"]')

    expect([fold.attributes('data-state'), fold.get('button').text()]).toEqual([
      'closed',
      'Options: Skip prompts, loop',
    ])
    page.unmount()
  })

  test('each_option_says_in_one_line_what_it_does', async () => {
    const { page } = await form(build)

    expect([
      help(page, '[value="acceptEdits"]'),
      help(page, '[value="bypassPermissions"]'),
      help(page, '#agent-loop'),
    ]).toEqual([
      'The agent edits files on its own and asks you before anything else.',
      'The agent asks nothing; the sandbox still blocks the network, secrets and writes outside the worktree.',
      'The agent starts again until the stage is done, instead of stopping after one try.',
    ])
    page.unmount()
  })
})

// A finished build is offered for review only when nothing else waits: not an open question, not
// an open review finding.
describe('a finished build', () => {
  const golden = view as { card?: Record<string, unknown> | null }
  const done = {
    ...(view as object),
    current_stage: 'build',
    work_done: true,
    runs: [],
    questions: [],
    card: { ...(golden.card ?? {}), holder: undefined, queue: undefined },
    subagents: [],
  }
  const question = {
    document: 'requirements.md',
    index: 1,
    text: 'Which currency?',
    choices: [],
    several: false,
    answer: '',
    answered_by: '',
  }
  const finding = {
    id: 'F1',
    severity: 'major',
    file: 'src/a.ts',
    line: 3,
    text: 'Off by one',
    state: 'open',
    reason: '',
    by: 'reviewer',
  }
  const agent = (page: VueWrapper) => page.get('section[aria-labelledby="agent-heading"]')
  const buttons = (page: VueWrapper) =>
    agent(page)
      .findAll('button')
      .map((b) => b.text())

  test('waits_for_review_with_review_offered_when_nothing_is_open', async () => {
    const { page } = await form(done)

    expect(agent(page).text()).toContain('Done and waiting for review.')
    expect(buttons(page)).toEqual(['Review with an agent'])
    page.unmount()
  })

  test('says_it_waits_for_an_answer_and_offers_no_review_while_a_question_is_open', async () => {
    const { page } = await form({ ...done, questions: [question] })

    expect(agent(page).text()).toContain('Waiting for an answer before review.')
    expect(agent(page).text()).not.toContain('Done and waiting for review.')
    expect(buttons(page)).toEqual([])
    page.unmount()
  })

  test('never_says_it_waits_for_review_while_its_ship_failed', async () => {
    const failed = {
      ...done,
      card: {
        ...done.card,
        delivery_event: { kind: 'ship_failed', at: 1, retry_at: null, reason: 'push rejected' },
      },
    }
    const { page } = await form(failed)

    expect(agent(page).text()).toContain(
      'Its ship failed: retry it from the alert under the title.',
    )
    expect(agent(page).text()).not.toContain('Done and waiting for review.')
    page.unmount()
  })

  test('says_a_fix_is_due_and_offers_the_builder_while_a_finding_is_open', async () => {
    const { page } = await form(done, false, { '/findings': { findings: [finding] } })

    expect(agent(page).text()).toContain('A fix is due: 1 review finding open.')
    expect(buttons(page)).toEqual(['Start agent'])
    page.unmount()
  })

  // The ticket's s key sends what its Start agent button sends, and e takes the person to the title.
  test('s_sends_what_start_agent_sends_and_e_focuses_the_title', async () => {
    const clicked = await form(done, false, { '/findings': { findings: [finding] } })
    const button = clicked.page.findAll('button').find((b) => b.text() === 'Start agent')
    await button?.trigger('click')
    await flushPromises()
    clicked.page.unmount()

    const keyed = await form(done, false, { '/findings': { findings: [finding] } })
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 's', bubbles: true }))
    await flushPromises()
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'e', bubbles: true }))

    expect({
      sent: keyed.changes,
      focused: document.activeElement?.getAttribute('name'),
    }).toEqual({ sent: clicked.changes, focused: 'title' })
    expect(clicked.changes).toHaveLength(1)
    keyed.page.unmount()
  })
})
