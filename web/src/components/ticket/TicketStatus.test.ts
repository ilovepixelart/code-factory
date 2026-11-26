// @vitest-environment happy-dom
// CF-1200: the ticket page says where the ticket stands, from the records its answer holds.

import type { VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { form, view } from '../../test/ticketForm'
import { GitPullRequestIcon } from '@hugeicons/core-free-icons'
import { draws } from '../../test/icons'

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

const golden = view as { card?: Record<string, unknown> | null }

/** The ticket view with the Status records given. */
function standing(extra: Record<string, unknown>) {
  return {
    ...(view as object),
    current_stage: 'build',
    card: { ...(golden.card ?? {}), hold: null, pull: null, holder: undefined, queue: undefined },
    columns: { spec: 3600, build: 1800, review: null },
    status: { conflict: null, capture: null },
    ...extra,
  }
}

const row = (page: { find: (s: string) => { text: () => string } }, name: string) =>
  page.find(`[data-status="${name}"]`).text().replace(/\s+/g, ' ').trim()
/** The pull request as the line shows it: its number, its state badge, then CI and review. */
const pullOf = (page: Awaited<ReturnType<typeof form>>['page']): string | null =>
  page.find('[data-status="pull"]').exists()
    ? page
        .findAll('[data-status="pull"] > *')
        .map((part) => part.text().trim())
        .join(' ')
    : null

test('ticket_status_shows_a_named_agent_and_a_pending_retry', async () => {
  const working = await form(
    standing({
      card: {
        ...(golden.card ?? {}),
        open_questions: 0,
        runs: [{ stage: 'build', agent: 'Claude', started_at: Date.now() / 1000 - 20 }],
      },
    }),
  )
  expect(working.page.find('[data-delivery-status] [role="status"]').text()).toBe('Claude · Build')
  working.page.unmount()

  const interrupted = await form(
    standing({
      card: {
        ...(golden.card ?? {}),
        open_questions: 0,
        runs: [],
        delivery_event: { kind: 'merge_failed', retry_at: Date.now() / 1000 + 30 },
      },
    }),
  )
  expect(interrupted.page.find('[data-delivery-status]').text()).toContain('retry in')
  interrupted.page.unmount()
})

// CF-1200-R1, R2: nothing holds it, so no `needs` clause, no queue; an hour in Spec, 30 minutes in
// Build now.
test('ticket_status_says_what_holds_it_and_time_in_each_column', async () => {
  const { page } = await form(standing({}))

  expect(row(page, 'stage')).toBe('Build for 30m')
  expect(row(page, 'time')).toBe('Spec 1h · Build 30m now · Review not entered')
  page.unmount()

  // No recorded move: the column it is in reads `now`, the others `not entered`.
  const unrecorded = await form(standing({ columns: { spec: null, build: null, review: null } }))
  expect(row(unrecorded.page, 'stage')).toBe('In Build')
  expect(row(unrecorded.page, 'time')).toBe('Spec not entered · Build now · Review not entered')
  unrecorded.page.unmount()
})

// CF-1200-R1: the card's hold in its words and its place in the queue.
test('ticket_status_names_the_hold_and_queue', async () => {
  const card = {
    ...(golden.card ?? {}),
    hold: { stage: 'build', detail: 'a commit on feat/CF-1', summary: 'a commit on feat/CF-1' },
    pull: null,
    holder: 'builder',
  }
  const { page } = await form(standing({ card }))

  expect(row(page, 'stage')).toBe('Build for 30m · needs a commit on feat/CF-1 · builder working')
  page.unmount()

  const free = await form(standing({ card: { ...card, hold: null } }))
  expect(row(free.page, 'stage')).toBe('Build for 30m · builder working')
  free.page.unmount()
})

// A pull request whose CI the board has not recorded says nothing of CI.
test('ticket_status_leaves_out_a_ci_state_not_recorded', async () => {
  const pull = { state: 'open', ci: '', head: 'h', url: 'https://github.com/o/r/pull/15', at: '' }
  const { page } = await form(standing({ card: { ...(golden.card ?? {}), hold: null, pull } }))

  expect(pullOf(page)).toBe('#15 Open')
  page.unmount()
})

// CF-1200-R3: the pull request by number with its state and a failed CI in the error tone.
test('ticket_status_shows_the_pull_request', async () => {
  const pull = {
    state: 'open',
    ci: 'failed',
    head: 'h',
    url: 'https://github.com/o/r/pull/7',
    at: '',
  }
  const { page } = await form(standing({ card: { ...(golden.card ?? {}), hold: null, pull } }))

  expect(pullOf(page)).toBe('#7 Open CI failed')
  expect(page.find('[data-status="pull"] .text-destructive').text()).toBe('CI failed')
  // CF-1226: the pull request icon, and a link that is underlined before any hover.
  const link = page.find('[data-status="pull"] a')
  expect(link.attributes('href')).toBe('https://github.com/o/r/pull/7')
  expect(link.findAll('svg')).toHaveLength(1)
  expect(draws(link.find('svg').element, GitPullRequestIcon)).toBe(true)
  expect(link.classes()).toContain('underline')
  expect(link.classes()).not.toContain('hover:underline')
  page.unmount()

  // No pull request, no part of the line for one.
  const none = await form(standing({}))
  expect(pullOf(none.page)).toBe(null)
  none.page.unmount()
})

// CF-1200-R7: a conflict on the tip is an Alert; none found said so quietly; no branch, nothing.
test('ticket_status_shows_a_merge_conflict', async () => {
  const conflicted = await form(
    standing({
      status: { conflict: { tip: 't', with: 'main', files: 'src/a.rs' }, capture: null },
    }),
  )
  expect([
    conflicted.page.get('[data-status="conflict"]').attributes('data-slot'),
    conflicted.page.get('[data-status="conflict"] [data-slot="alert-description"]').text().trim(),
  ]).toEqual(['alert', 'Conflicts with main in src/a.rs'])
  conflicted.page.unmount()

  const clean = await form(standing({ status: { conflict: { tip: 't' }, capture: null } }))
  expect(row(clean.page, 'conflict')).toBe('No conflict found')
  clean.page.unmount()

  const branchless = await form(standing({}))
  expect(branchless.page.find('[data-status="conflict"]').exists()).toBe(false)
  branchless.page.unmount()
})

const action = (page: Awaited<ReturnType<typeof form>>['page']) => page.find('[data-status="next"]')
const starts = (page: Awaited<ReturnType<typeof form>>['page']) =>
  page.findAll('button').filter((b) => b.text() === 'Start agent').length

// CF-1206: the one next action. A Build ticket nobody works on offers Start agent once, in its
// Agent section, which starts a run; the Status section does not repeat it.
test('the_panel_offers_start_agent_once_and_it_starts_a_run', async () => {
  const { page, changes, bodies } = await form(
    standing({ work_done: false, runs: [], questions: [] }),
  )
  const starts = page.findAll('button').filter((b) => b.text() === 'Start agent')

  expect(action(page).exists()).toBe(false)
  expect(starts.map((b) => b.element.closest('section')?.getAttribute('aria-labelledby'))).toEqual([
    'agent-heading',
  ])
  await starts[0]?.trigger('click')
  expect(changes).toEqual(['POST /api/tickets/sample/CF-1/runs'])
  expect(bodies).toEqual([{ permissions: 'bypassPermissions', loop: true }])
  page.unmount()
})

// CF-1206: a run at work, or work done, leaves nothing to start.
test('the_panel_offers_no_start_while_a_run_works_or_work_is_done', async () => {
  const working = await form(
    standing({
      work_done: false,
      questions: [],
      runs: [
        {
          id: 'r',
          stage: 'build',
          iteration: 1,
          loop: false,
          started_at: 0,
          progress: {
            tool_calls: null,
            reads: null,
            changes: null,
            files: null,
            tokens: null,
            last_activity: null,
          },
          memory: null,
          context_at: null,
        },
      ],
    }),
  )
  expect(starts(working.page)).toBe(0)
  working.page.unmount()

  const done = await form(standing({ work_done: true, runs: [], questions: [] }))
  expect(starts(done.page)).toBe(0)
  done.page.unmount()
})

// The status says where the ticket stands and offers no shortcut to what sits on the page already:
// no Answer questions over the questions, no Open pull request beside the pull request's link.
test('ticket_status_repeats_no_action_the_page_already_holds', async () => {
  const pull = {
    state: 'open',
    ci: 'none',
    head: 'h',
    url: 'https://github.com/o/r/pull/7',
    at: '',
  }
  const question = {
    text: 'Which one?',
    document: 'spec',
    index: 0,
    several: false,
    choices: [],
    answer: '',
  }
  const { page } = await form(
    standing({
      current_stage: 'review',
      runs: [],
      questions: [question],
      card: { ...(golden.card ?? {}), hold: null, pull },
    }),
  )
  const words = page.findAll('button, a').map((b) => b.text().trim())

  expect({
    next: page.find('[data-status="next"]').exists(),
    answer: words.includes('Answer questions'),
    open: words.includes('Open pull request'),
    link: page.find('[data-status="pull"] a').attributes('href'),
  }).toEqual({ next: false, answer: false, open: false, link: 'https://github.com/o/r/pull/7' })
  page.unmount()
})

// The stage is said once: one glyph and its words under the title, no step bar repeating it.
test('the_stage_is_said_once', async () => {
  const { page } = await form(standing({}))

  expect({
    steps: page.find('[data-status="steps"]').exists(),
    stages: page.findAll('[data-header-stage]').length,
    glyph: page.find('[data-header-stage] svg[data-shape="half"]').exists(),
  }).toEqual({ steps: false, stages: 1, glyph: true })
  page.unmount()
})

// At Review the Status lists what the merge waits on, each ticked or open, and offers Merge only
// when every one is ticked; Merge posts the same merge the Inbox's Ready to merge does.
describe('the merge path at Review', () => {
  const pull = { url: 'https://github.com/o/r/pull/12', state: 'open', ci: 'passed', review: '' }
  const atReview = (check: unknown) =>
    standing({
      current_stage: 'review',
      card: { ...(golden.card ?? {}), open_questions: 0, runs: [], pull, check },
    })
  const items = (page: VueWrapper) =>
    page
      .findAll('[data-status="merge"] li')
      .map((li) => `${li.attributes('data-done') ?? ''}:${li.text().trim()}`)

  test('every_item_ticked_offers_merge_and_merge_posts_it', async () => {
    const { page, changes } = await form(atReview({ passed: true, commit: '39c486b' }))

    expect(items(page)).toEqual([
      'true:Pull request open',
      'true:Checks passed on 39c486b',
      'true:CI passed',
      'true:No open review findings',
    ])
    await page.get('[data-status="merge"] button').trigger('click')
    expect(changes).toContain('POST /api/tickets/sample/CF-1/merge')
    page.unmount()
  })

  test('a_failed_check_is_an_open_item_and_offers_no_merge', async () => {
    const { page } = await form(atReview({ passed: false, commit: '39c486b' }))

    expect(items(page)[1]).toBe('false:Checks failed on 39c486b')
    expect(page.find('[data-status="merge"] button').exists()).toBe(false)
    page.unmount()
  })
})

// A failed ship names its reason and how long ago, and offers to ship again; the press posts the
// ticket's ship.
test('ticket_status_names_a_failed_ships_reason_and_offers_a_retry', async () => {
  const { page, changes } = await form(
    standing({
      card: {
        ...(golden.card ?? {}),
        open_questions: 0,
        runs: [],
        delivery_event: {
          kind: 'ship_failed',
          at: Date.now() / 1000 - 120,
          retry_at: null,
          reason: 'push rejected (non-fast-forward)',
        },
      },
    }),
  )
  const failure = page.get('[data-status="failure"]')

  expect(failure.text().replace(/\s+/g, ' ')).toContain(
    'Ship failed 2m ago: push rejected (non-fast-forward)',
  )
  const retry = failure.get('button')
  // Short on screen, as the Alert's action; named in full for a screen reader.
  expect([retry.text(), retry.attributes('aria-label')]).toEqual(['Retry', 'Retry ship'])
  await retry.trigger('click')
  expect(changes).toContain('POST /api/tickets/sample/CF-1/ship')
  page.unmount()
})
