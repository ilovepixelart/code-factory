// CF-317: a card's session link navigates inside the app, so the board's selection and notice
// survive it.

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, test, vi } from 'vitest'
import type { Card } from '@/lib/board'
import { ESTIMATE_NOTE } from '@/lib/format'
import { goldenBoard, memoryRouter, provideBoard } from '../../support/board'
import { present } from '../../support/present'
import TicketCard from '@/components/TicketCard.vue'
import { TONE_VARIANTS } from '@/lib/status_tone'
import { GitPullRequestIcon } from '@hugeicons/core-free-icons'
import { draws } from '../../support/icons'

const board = goldenBoard()

describe('a card with a session', () => {
  test('a_session_link_stays_in_the_app', async () => {
    const card = present(
      Object.values(board.columns)
        .flat()
        .find((c: Card) => c.sessions.length > 0),
      'a card with a session',
    )
    const router = memoryRouter()
    await router.push('/tickets')
    const view = mount(TicketCard, {
      props: { card, stage: card.stage, today: board.today },
      global: {
        plugins: [router],
        provide: provideBoard(board),
        stubs: { CardMenu: true },
      },
    })
    const id = present(card.sessions[0], 'its session').session_id
    const link = view.find(`a[href="/sessions/${id}"]`)

    await link.trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.fullPath).toBe(`/sessions/${id}`)
  })
})

describe('a card in the agent queue', () => {
  const meta = (queue?: string, overlap?: string) => {
    const card: Card = {
      ...present(board.columns.spec[0], 'a card'),
      ...(queue === undefined ? {} : { queue }),
      ...(overlap === undefined ? {} : { overlap }),
    }
    const view = mount(TicketCard, {
      props: { card, stage: card.stage, today: board.today },
      global: {
        plugins: [memoryRouter()],
        provide: provideBoard(board),
        stubs: { CardMenu: true },
      },
    })
    return view.find('[data-js-queue]')
  }

  test('a_card_says_next_up_or_which_limit_holds_it', () => {
    const next = meta('next')
    const held = meta('Build 1 of 1')

    expect(next.text()).toBe('Next up')
    expect(next.classes()).toContain('text-muted-foreground')
    expect(held.text()).toBe('Held: Build 1 of 1')
    expect(meta().exists()).toBe(false)
  })

  // CF-1453: a ticket that starts beside an open pull request says which one it likely overlaps.
  test('a_card_says_which_pull_request_it_likely_overlaps', () => {
    expect(meta('next', 'likely overlaps #5 in a.rs').text()).toBe(
      'Next up, likely overlaps #5 in a.rs',
    )
  })
})

describe('a card held by an agent', () => {
  const label = (change: Partial<Card>) => {
    const card: Card = { ...present(board.columns.spec[0], 'a card'), ...change }
    const view = mount(TicketCard, {
      props: { card, stage: card.stage, today: board.today },
      global: {
        plugins: [memoryRouter()],
        provide: provideBoard(board),
        stubs: { CardMenu: true },
      },
    })
    return view.find('[data-js-queue]')
  }

  // CF-360-R13: the defined agent holding the ticket shows where Next up and Held: go.
  test('a_card_says_which_agent_works_it', () => {
    const working = label({ holder: 'writer' })
    const held = label({ queue: 'Build 1 of 1' })

    expect(working.text()).toBe('writer working')
    expect(working.classes()).toContain('text-muted-foreground')
    expect(held.text()).toBe('Held: Build 1 of 1')
  })
})

describe('a card waiting on a usage limit', () => {
  const now = 1_790_001_000
  afterEach(() => {
    vi.useRealTimers()
  })
  const shown = (limited_until: number | null) => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(now * 1000)
    const card: Card = { ...present(board.columns.spec[0], 'a card'), limited_until }
    const view = mount(TicketCard, {
      props: { card, stage: card.stage, today: board.today },
      global: {
        plugins: [memoryRouter()],
        provide: provideBoard(board),
        stubs: { CardMenu: true },
      },
    })
    return view.text().replace(/\s+/g, ' ')
  }

  // CF-395-R10: a ticket whose latest run met a usage limit says when it starts again.
  test('a_parked_ticket_card_says_when_it_resumes', () => {
    expect(shown(now + 7500)).toContain('Usage limit: resumes in 2.1h')
    expect(shown(now - 10)).toContain('Usage limit: resuming')
    expect(shown(null)).not.toContain('Usage limit')
  })
})

// CF-1205: a column is read from git, so what holds a card is the column itself: the card does
// not restate it, and its due date reads with a space between its state and the day.
describe('a card in its column', () => {
  const mounted = async (change: Partial<Card>) => {
    const golden = present(Object.values(board.columns).flat()[0], 'a card')
    const card: Card = { ...golden, ...change }
    const router = memoryRouter()
    await router.push('/tickets')
    return mount(TicketCard, {
      props: { card, stage: card.stage, today: board.today },
      global: { plugins: [router], provide: provideBoard(board), stubs: { CardMenu: true } },
    })
  }

  test('a_card_does_not_restate_its_column', async () => {
    const held = await mounted({ hold: { stage: 'build', detail: 'a commit on feat/CF-2' } })

    expect(held.text()).not.toContain('a commit on feat/CF-2')
    expect(held.text()).not.toContain('needs Build')
  })

  test('an_overdue_date_reads_with_a_space', async () => {
    const late = await mounted({ due: '2026-10-10', due_date: '2026-10-10', due_state: 'overdue' })

    expect(late.get('[title="Due 2026-10-10"]').text()).toMatch(/^overdue \d+ Oct$/)
  })
})

describe('a card in plain words (CF-1076)', () => {
  const shown = (change: Partial<Card>, repositories: string[] = ['code-factory']) => {
    const card: Card = { ...present(board.columns.spec[0], 'a card'), ...change }
    const options = { ...board.options, repository: repositories }
    return mount(TicketCard, {
      props: { card, stage: card.stage, today: board.today },
      global: {
        plugins: [memoryRouter()],
        provide: provideBoard({ ...board, options }),
        stubs: { CardMenu: true },
      },
    })
  }

  // CF-1076-R2: a reason that starts by saying it stopped reads once, capitalised, its numbers
  // grouped even as recorded before the board grouped them.
  test('a_halt_reads_once', () => {
    const stopped = shown({ halted: 'stopped at its cap: flint 3000233 of 3000000 tokens' })
    const other = shown({ halted: 'no progress at Spec' })

    const badge = (view: ReturnType<typeof shown>) =>
      view
        .findAll('[data-slot="badge"]')
        .find((b) => b.text().includes('Stop') || b.text().includes('progress'))
    expect(badge(stopped)?.text()).toBe('Stopped at its cap: flint 3,000,233 of 3,000,000 tokens')
    expect(badge(other)?.text()).toBe('Stopped: no progress at Spec')
  })

  // CF-1076-R3: of a working session and an ended one, only the working one is listed.
  test('a_card_leaves_out_ended_sessions', () => {
    const session = present(
      Object.values(board.columns)
        .flat()
        .find((c: Card) => c.sessions.length > 0)?.sessions[0],
      'a session',
    )
    const view = shown({
      sessions: [
        { ...session, session_id: 'working-one', state: 'working' },
        { ...session, session_id: 'ended-one', state: 'ended' },
      ],
    })

    expect(view.find('a[href="/sessions/working-one"]').exists()).toBe(true)
    expect(view.find('a[href="/sessions/ended-one"]').exists()).toBe(false)
  })

  // CF-1076-R4: the folder shows beside another tracked repository, not alone.
  test('the_folder_shows_only_beside_another_repository', () => {
    const alone = shown({ repository: 'code-factory' }, ['code-factory'])
    const two = shown({ repository: 'code-factory' }, ['code-factory', 'api'])

    const folder = (view: ReturnType<typeof shown>) =>
      view.findAll('span').some((s) => s.text() === 'code-factory' && s.find('svg').exists())
    expect(folder(alone)).toBe(false)
    expect(folder(two)).toBe(true)
  })

  const footer = (view: ReturnType<typeof shown>) => view.find('[data-card-footer]')

  const pull = (ci: string, state: string) => ({
    state,
    ci,
    head: 'abc',
    url: 'https://example.invalid/pull/1',
    at: '2026-11-06T10:00:00Z',
  })
  const pullLine = (view: ReturnType<typeof shown>) =>
    view.find('a[title="The pull request on GitHub"]').text().replace(/\s+/g, ' ')

  // CF-1097-R1
  test('a_pull_without_ci_says_nothing_of_ci', () => {
    const view = shown({ pull: pull('none', 'merged') })

    expect(pullLine(view)).toBe('PR #1 Merged')
    expect(view.find('[data-pull-state]').attributes('data-variant')).toBe(TONE_VARIANTS.success)
  })

  // CF-1097-R1
  test('a_pull_with_failed_ci_says_checks_failing', () => {
    const view = shown({ pull: pull('failed', 'open') })

    expect(pullLine(view)).toBe('PR #1 Checks failing')
    expect(view.find('[data-pull-state]').attributes('data-variant')).toBe(TONE_VARIANTS.error)
  })

  // CF-1318: the board's failed checks are said once, as the card's text, on every card; the
  // label says the pull request's own state.
  const check = (passed: boolean) => ({ passed, commit: 'abcdef0123456' })
  const metaText = (view: ReturnType<typeof shown>) => view.text().replace(/\s+/g, ' ')
  const failures = (view: ReturnType<typeof shown>) =>
    metaText(view).match(/checks fail/gi)?.length ?? 0

  test('a_failed_check_beside_an_open_pull_request_is_the_text_and_the_label_says_open', () => {
    const view = shown({ pull: pull('none', 'open'), check: check(false) })

    expect(pullLine(view)).toBe('PR #1 Open')
    expect(failures(view)).toBe(1)
    expect(view.find('span.text-destructive').attributes('title')).toBe('On abcdef0')
  })

  test('a_failed_check_beside_a_merged_pull_request_is_the_same_text', () => {
    const view = shown({ pull: pull('none', 'merged'), check: check(false) })

    expect(pullLine(view)).toBe('PR #1 Merged')
    expect(failures(view)).toBe(1)
  })

  test('a_failed_check_is_not_said_again_by_a_failed_status_of_the_pull_request', () => {
    const view = shown({ pull: pull('failed', 'open'), check: check(false) })

    expect(pullLine(view)).toBe('PR #1 Open')
    expect(failures(view)).toBe(1)
  })

  test('a_failed_check_beside_a_conflict_says_both', () => {
    const view = shown({
      pull: { ...pull('none', 'open'), conflict: true },
      check: check(false),
    })

    expect(pullLine(view)).toBe('PR #1 Conflict')
    expect(metaText(view)).toContain('Checks failed')
  })

  test('a_failed_check_without_a_pull_request_says_checks_failed', () => {
    const view = shown({ check: check(false) })

    expect(metaText(view)).toContain('Checks failed')
    expect(view.find('[data-pull-state]').exists()).toBe(false)
  })

  test('a_passed_check_beside_an_open_pull_request_says_passed_and_the_label', () => {
    const view = shown({ pull: pull('none', 'open'), check: check(true) })

    expect(metaText(view)).toContain('Checks passed')
    expect(pullLine(view)).toBe('PR #1 Open')
  })

  // CF-1226: an opened pull request has its own icon, apart from the branch line's.
  test('a_pull_shows_the_pull_request_icon', () => {
    const view = shown({ pull: pull('none', 'open') })
    const icons = view.find('a[title="The pull request on GitHub"]').findAll('svg')

    expect(icons).toHaveLength(1)
    expect(draws(icons[0]?.element, GitPullRequestIcon)).toBe(true)
  })

  // CF-1112-R1
  test('a_run_names_its_attempt', () => {
    const run = (id: string, attempt: number) => ({
      id,
      stage: 'build' as const,
      iteration: 1,
      loop: false,
      max_iterations: 1,
      attempt,
    })
    const runs = (view: ReturnType<typeof shown>) =>
      view
        .findAll('[data-slot="badge"]')
        .map((b) => b.text().replace(/\s+/g, ' '))
        .filter((words) => /^Agent · .* iteration \d/.test(words))

    expect(runs(shown({ runs: [run('r1', 1), run('r2', 2)] }))).toEqual([
      'Agent · Build · attempt 1 · iteration 1',
      'Agent · Build · attempt 2 · iteration 1',
    ])
    expect(runs(shown({ runs: [run('r3', 0)] }))).toEqual(['Agent · Build · iteration 1'])
  })

  // CF-1091-R1
  test('a_card_with_nothing_for_its_footer_has_none', () => {
    const view = shown({ repository: 'code-factory', branch: '', assignee: '' })

    expect(footer(view).exists()).toBe(false)
  })

  // CF-1096-R1: the card's own padding closes it with or without a footer; the footer is the
  // card's last part, after its body.
  test('a_card_without_a_footer_ends_on_its_body', () => {
    const slots = (view: ReturnType<typeof shown>) =>
      view.findAll('[data-slot="card"] > *').map((part) => part.attributes('data-slot'))
    const bare = shown({ repository: 'code-factory', branch: '', assignee: '' })
    const branched = shown({ repository: 'code-factory', branch: 'ticket/cf-1', assignee: '' })

    expect(slots(bare)).toEqual(['card-content'])
    expect(slots(branched)).toEqual(['card-content', 'card-footer'])
  })

  // CF-1091-R1
  test('a_card_with_a_branch_keeps_its_footer', () => {
    const view = shown({ repository: 'code-factory', branch: 'ticket/cf-1', assignee: '' })

    expect(footer(view).text()).toContain('ticket/cf-1')
  })
})

// CF-1216: a spend that holds the board's estimate is led by `~`, before the budget when
// there is one, and its tooltip says so; a spend of reported costs reads as it did.
describe("a card's spend", () => {
  const chip = (fields: Partial<Card>) => {
    const card: Card = { ...present(board.columns.spec[0], 'a card'), ...fields }
    const view = mount(TicketCard, {
      props: { card, stage: card.stage, today: board.today },
      global: {
        plugins: [memoryRouter()],
        provide: provideBoard(board),
        stubs: { CardMenu: true },
      },
    })
    const found = view.findAll('span.tabular-nums').find((span) => /^~?\$/.test(span.text()))
    return found ? [found.text(), found.attributes('title')] : null
  }

  test('an_estimated_spend_is_marked_on_the_card', () => {
    expect([
      chip({ spent: 3.25, spent_estimated: true, budget: 2.5 }),
      chip({ spent: 3.25, spent_estimated: true, budget: null }),
      chip({ spent: 3.25, budget: 2.5 }),
      chip({ spent: 3.25, budget: null }),
      chip({ spent: 0, spent_estimated: true, budget: null }),
    ]).toEqual([
      ['~$3.25 of $2.50', `Agent spend against the ticket's budget; ${ESTIMATE_NOTE}`],
      ['~$3.25', `Cost of the agent runs on this ticket; ${ESTIMATE_NOTE}`],
      ['$3.25 of $2.50', "Agent spend against the ticket's budget"],
      ['$3.25', 'Cost reported by the agent runs on this ticket'],
      null,
    ])
  })
})

// How much a pull request asks a reviewer to read (docs/ui.md, The kanban): its lines added and
// removed beside its link, and Large past 400.
describe('the size of a pull request', () => {
  const shown = (change: Partial<Card>) => {
    const card: Card = { ...present(board.columns.spec[0], 'a card'), ...change }
    return mount(TicketCard, {
      props: { card, stage: card.stage, today: board.today },
      global: {
        plugins: [memoryRouter()],
        provide: provideBoard(board),
        stubs: { CardMenu: true },
      },
    })
  }
  const sized = (additions: number, deletions: number) => ({
    state: 'open',
    ci: 'none',
    head: 'h',
    url: 'https://example.invalid/pull/1',
    at: '0',
    additions,
    deletions,
    changed_files: 4,
  })

  test('a_counted_pull_request_shows_its_lines_and_a_large_one_says_so', () => {
    const small = shown({ pull: sized(86, 12) })
    const large = shown({ pull: sized(1240, 380) })

    const parts = (view: ReturnType<typeof shown>) =>
      view.findAll('[data-pull-size] > *').map((part) => part.text().replace(/\s+/g, ' '))

    expect([parts(small), parts(large)]).toEqual([['+86 −12'], ['+1,240 −380', 'Large']])
  })

  test('a_pull_request_without_a_count_shows_no_size', () => {
    const plain = {
      state: 'open',
      ci: 'none',
      head: 'h',
      url: 'https://example.invalid/pull/1',
      at: '0',
    }
    expect(shown({ pull: plain }).find('[data-pull-size]').exists()).toBe(false)
  })
})
