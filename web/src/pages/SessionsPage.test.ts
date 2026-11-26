// @vitest-environment happy-dom
// CF-324: "Show ended" is remembered in the board's own storage, like every other setting.
// CF-1194: the page reads the server's page of sessions and draws it with the page control.

import { variantOf } from '../test/button'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, test, vi } from 'vitest'
import type { PagedSessions, Session } from '../lib/sessions'
import { memoryRouter, provideBoard } from '../test/board'
import { present } from '../test/present'
import SessionsPage from './SessionsPage.vue'

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** Session `n` of `repository`, idle, the higher `n` the more recent; the API lists the most recent first. */
function session(n: number, repository = 'sample'): Session {
  return {
    session_id: `s-${String(n)}`,
    cwd: `/work/${repository}`,
    repository,
    branch: 'main',
    state: 'idle',
    last_event_at: 1_790_000_000 + n,
    stale: false,
    current_action: null,
    subagents: [],
    last_prompt: '',
    turn_tool_calls: 0,
  }
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

/** The server's first page of 50 holding `rows` of `total`, nothing waiting. */
function paged(rows: Session[], total = rows.length): PagedSessions {
  return {
    waiting: [],
    rows,
    total,
    page: 1,
    size: 50,
    ended_hidden: 0,
    counts: { waiting: 0, working: 0, idle: 0, stale: 0 },
    repositories: {},
  }
}

/** The sessions addresses the page asked for, in order. */
let asked: string[] = []
/** The usage addresses the page asked for, in order. */
let askedUsage: string[] = []

/** The page at `address` over a board answering `listed`, its usage answered by `usage` when given. */
async function page(
  listed: PagedSessions = paged([]),
  usage?: Held,
  address = '/',
): Promise<VueWrapper> {
  document.body.innerHTML = '<div id="header-controls"></div><div id="app"></div>'
  asked = []
  askedUsage = []
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      if (url.startsWith('/api/sessions/usage')) {
        askedUsage.push(url)
        return usage?.promise ?? Promise.resolve(json({}))
      }
      if (url.startsWith('/api/sessions?')) asked.push(url)
      return Promise.resolve(url.startsWith('/api/sessions?') ? json(listed) : json({}))
    }),
  )
  const router = memoryRouter()
  await router.push(address)
  const view = mount(SessionsPage, {
    attachTo: '#app',
    global: { plugins: [router], provide: provideBoard() },
  })
  await flushPromises()
  return view
}

const toggle = () => present(document.querySelector<HTMLElement>('[role="switch"]'), 'the toggle')

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
  document.body.innerHTML = ''
})

describe('Show ended', () => {
  test('show_ended_is_remembered_in_storage', async () => {
    const first = await page()
    toggle().click()
    await flushPromises()
    first.unmount()

    const second = await page()

    expect(localStorage.getItem('codeFactoryShowEnded')).toBe('1')
    expect(toggle().getAttribute('aria-checked')).toBe('true')
    expect(asked[0]).toBe('/api/sessions?page=1&size=50&ended=1')
    second.unmount()
  })
})

const rows = () => document.querySelectorAll('[aria-label="Sessions in sample"] > [data-session]')
const pager = () => document.querySelector('nav[aria-label="Pages of sessions"]')

describe('a long list', () => {
  // CF-1086-R1
  test('lists_sessions_before_the_usage_answers', async () => {
    const view = await page(paged([session(1), session(2)]), held())

    expect(rows()).toHaveLength(2)
    expect(document.body.textContent).toContain('no cost yet')
    view.unmount()
  })

  // CF-1086-R1
  test('the_costs_fill_in_when_the_usage_answers', async () => {
    const usage = held()
    const view = await page(paged([session(1)]), usage)
    usage.resolve(
      json({
        's-1': {
          input: 1,
          output: 2,
          cache_read: 0,
          cache_write: 0,
          cost: 3.5,
          reported_at: 1_790_000_000,
          cost_incomplete: false,
        },
      }),
    )
    await flushPromises()

    expect(document.body.textContent).toContain('$3.50')
    view.unmount()
  })

  // CF-1194
  test('the_first_page_is_asked_of_the_server_and_paged', async () => {
    const view = await page(
      paged(
        Array.from({ length: 50 }, (_, i) => session(120 - i)),
        120,
      ),
    )

    expect(asked[0]).toBe('/api/sessions?page=1&size=50')
    expect(rows()).toHaveLength(50)
    expect(rows()[0]?.getAttribute('data-session')).toBe('s-120')
    expect(pager()?.textContent).toContain('1 to 50 of 120')
    view.unmount()
  })

  // CF-1260
  test('usage_is_asked_for_the_shown_sessions_alone', async () => {
    const listed = { ...paged([session(1), session(2)]), waiting: [session(9)] }
    const view = await page(listed)

    expect(askedUsage).toEqual(['/api/sessions/usage?session=s-9&session=s-1&session=s-2'])
    view.unmount()
  })

  // CF-1260: an empty page names no session, and no session named is every session's usage.
  test('no_usage_is_asked_when_no_session_is_shown', async () => {
    const view = await page(paged([]))

    expect(askedUsage).toEqual([])
    view.unmount()
  })

  // CF-1194
  test('the_address_names_the_page_the_server_answers', async () => {
    const view = await page(paged([session(1)]), undefined, '/?page=2&size=25')

    expect(asked[0]).toBe('/api/sessions?page=2&size=25')
    view.unmount()
  })

  // CF-1194
  test('a_list_that_fits_one_page_shows_no_page_control', async () => {
    const view = await page(paged([session(2), session(1)]))

    expect(pager()).toBeNull()
    view.unmount()
  })

  // CF-1194: the groups keep the server's order, a newer repository after an older one included.
  test('the_page_groups_its_rows_by_repository_in_the_servers_order', async () => {
    const view = await page(paged([session(1, 'older'), session(2, 'older'), session(9, 'newer')]))

    const groups = [...document.querySelectorAll('[aria-label^="Sessions in "]')].map((g) =>
      g.getAttribute('aria-label'),
    )
    expect(groups).toEqual(['Sessions in older', 'Sessions in newer'])
    view.unmount()
  })
})

// CF-1204: waiting sessions as cards, filter chips by state, no count that a page contradicts.
describe('the sessions overview', () => {
  const working = (n: number): Session => ({ ...session(n), state: 'working' })
  const stale = (n: number): Session => ({ ...session(n), state: 'working', stale: true })
  const blocked = (n: number): Session => ({ ...session(n), state: 'blocked' })
  // The counts are the server's, over every page: more than the four rows this page holds.
  const mixed = (): PagedSessions => ({
    ...paged([working(1), working(2), session(3), stale(4)]),
    waiting: [blocked(5)],
    counts: { waiting: 1, working: 120, idle: 7, stale: 3 },
  })
  const chip = (name: string) =>
    [...document.querySelectorAll<HTMLAnchorElement>('nav[aria-label="Filter by state"] a')].find(
      (a) => a.textContent.startsWith(name),
    )

  test('waiting_sessions_are_cards_with_open_session', async () => {
    const view = await page(mixed())

    const cards = document.querySelectorAll('[aria-label="Blocked sessions"] > [data-session]')
    expect(cards).toHaveLength(1)
    expect(cards[0]?.textContent).toContain('Open session')
    view.unmount()
  })

  test('only_the_longest_wait_takes_the_primary_button', async () => {
    const view = await page({ ...mixed(), waiting: [blocked(5), blocked(6)] })

    const buttons = [
      ...document.querySelectorAll('[aria-label="Blocked sessions"] a[data-slot="button"]'),
    ]
    expect(buttons.map((b) => variantOf(b))).toEqual(['default', 'secondary'])
    view.unmount()
  })

  test('chips_count_each_state_and_the_current_one_is_marked', async () => {
    const view = await page(mixed(), undefined, '/?state=working')

    expect(chip('waiting')?.textContent).toBe('waiting1')
    expect(chip('working')?.textContent).toBe('working120')
    expect(chip('idle')?.textContent).toBe('idle7')
    expect(chip('stale')?.textContent).toBe('stale3')
    expect(chip('working')?.getAttribute('aria-current')).toBe('page')
    expect(chip('All')?.getAttribute('aria-current')).toBeNull()
    view.unmount()
  })

  // CF-1265: the server applies the state before paging; the page asks for it and draws the answer.
  test('a_state_filter_is_asked_of_the_server_and_hides_the_waiting_cards', async () => {
    const answer = { ...mixed(), rows: [working(1), working(2)], waiting: [], total: 120 }
    const view = await page(answer, undefined, '/?state=working&page=3')

    expect(asked[0]).toBe('/api/sessions?page=3&size=50&state=working')
    const ids = [...document.querySelectorAll('[data-slot="card"][data-session]')].map((r) =>
      r.getAttribute('data-session'),
    )
    expect(ids).toEqual(['s-1', 's-2'])
    expect(document.querySelector('[aria-label="Blocked sessions"]')).toBeNull()
    view.unmount()
  })

  // CF-1265: a chip's link leaves the page behind, so the first page of its state is read.
  test('a_chip_link_names_its_state_and_no_page', async () => {
    const view = await page({ ...mixed(), page: 3 }, undefined, '/?state=idle&page=3')

    expect(chip('working')?.getAttribute('href')).toBe('/?state=working')
    expect(chip('All')?.getAttribute('href')).toBe('/')
    view.unmount()
  })

  // CF-1265: 120 working sessions on pages of 50: the third holds 20 rows of the working ones.
  test('the_third_page_of_120_working_sessions_holds_twenty_rows', async () => {
    const last = Array.from({ length: 20 }, (_, i) => working(20 - i))
    const answer = {
      ...paged(last, 120),
      page: 3,
      counts: { waiting: 0, working: 120, idle: 0, stale: 0 },
    }
    const view = await page(answer, undefined, '/?state=working&page=3')

    expect(asked[0]).toBe('/api/sessions?page=3&size=50&state=working')
    expect(rows()).toHaveLength(20)
    expect(chip('working')?.textContent).toBe('working120')
    expect(pager()?.textContent).toContain('101 to 120 of 120')
    view.unmount()
  })

  // CF-1265: the page does not count the rows it holds: 120 working sessions on a page of 50.
  test('the_working_chip_and_the_section_read_the_whole_list', async () => {
    const rows50 = Array.from({ length: 50 }, (_, i) => working(i + 1))
    const answer = {
      ...paged(rows50, 120),
      counts: { waiting: 0, working: 120, idle: 0, stale: 0 },
    }
    const view = await page(answer, undefined, '/?state=working')

    expect(chip('working')?.textContent).toBe('working120')
    expect(pager()?.textContent).toContain('1 to 50 of 120')
    view.unmount()
  })

  test('the_waiting_filter_shows_only_the_waiting_cards', async () => {
    const view = await page(mixed(), undefined, '/?state=waiting')

    const ids = [
      ...document.querySelectorAll('[aria-label="Blocked sessions"] [data-session]'),
    ].map((r) => r.getAttribute('data-session'))
    expect(ids).toEqual(['s-5'])
    view.unmount()
  })

  test('the_state_tabs_stay_under_the_waiting_filter_with_waiting_current', async () => {
    const view = await page(mixed(), undefined, '/?state=waiting')

    const links = [...document.querySelectorAll('nav[aria-label="Filter by state"] a')]
    expect(links.map((a) => a.textContent.trim())).toEqual([
      'All',
      'waiting1',
      'working120',
      'idle7',
      'stale3',
    ])
    expect(chip('waiting')?.getAttribute('aria-current')).toBe('page')
    view.unmount()
  })

  // CF-1265: a heading's count is the repository's, from the answer, not the rows of the page.
  test('a_group_heading_carries_the_repositorys_count_from_the_answer', async () => {
    const answer = { ...paged([session(1), session(2)], 120), repositories: { sample: 120 } }
    const view = await page(answer)

    expect(document.querySelector('h3')?.textContent.trim()).toBe('sample120')
    view.unmount()
  })
})

// The owner: a filter with nothing to filter does not show; a chosen one stays, the way back to All.
describe('the state filter follows the sessions', () => {
  const filterShown = (view: VueWrapper) => view.find('nav[aria-label="Filter by state"]').exists()

  test('with_no_sessions_the_state_filter_is_absent', async () => {
    expect(filterShown(await page(paged([])))).toBe(false)
  })

  test('with_sessions_the_state_filter_shows', async () => {
    const listed = { ...paged([session(1)]), counts: { waiting: 0, working: 1, idle: 0, stale: 0 } }

    expect(filterShown(await page(listed))).toBe(true)
  })

  test('a_chosen_state_keeps_the_filter_with_nothing_in_it', async () => {
    expect(filterShown(await page(paged([]), undefined, '/?state=working'))).toBe(true)
  })
})

// The owner: an empty list says so in a short title, the rest in the sentence under it.
describe('no session to list', () => {
  const said = () =>
    ['empty-title', 'empty-description'].map(
      (slot) =>
        document
          .querySelector(`[aria-labelledby="sessions-heading"] [data-slot="${slot}"]`)
          ?.textContent.trim() ?? null,
    )

  test('no_session_at_all_says_how_to_start_one', async () => {
    const view = await page(paged([]))

    const blocked = document.querySelector(
      '[aria-labelledby="attention-heading"] [data-slot="empty-description"]',
    )
    expect(blocked?.textContent.trim()).toBe(
      'Sessions that need an answer or permission appear here.',
    )
    expect(said()).toStrictEqual([
      'No sessions to show',
      'Start an agent on a ticket and its session shows here.',
    ])
    view.unmount()
  })

  test('ended_sessions_hidden_say_how_to_list_them', async () => {
    const view = await page({ ...paged([]), ended_hidden: 2 })

    expect(said()).toStrictEqual([
      'No live sessions',
      '2 ended sessions are hidden; turn on Show ended to list them.',
    ])
    view.unmount()
  })
})
