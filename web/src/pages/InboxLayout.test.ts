// @vitest-environment happy-dom
// CF-1196: the Inbox pages each section at 50 rows and lands a push link on its page, leads with
// what needs an act and keeps the sessions it cannot act on apart, and shows no standing warning
// about desktop notifications.

import { PRIMARY } from '../test/button'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { ATTENTION } from '../lib/attention'
import { SECTIONS, type Inbox, type InboxItem } from '../lib/metrics'
import { memoryRouter } from '../test/board'
import InboxPage from './InboxPage.vue'

const stopped = (n: number): InboxItem => ({
  since: 1_790_000_000 + n,
  kind: 'stopped',
  reason: 'the agent ran out of turns',
  note: '',
  count: 1,
  images: [],
  ticket: { repository: 'sample', id: `CF-${String(n)}`, title: `Ticket ${String(n)}` },
  question: null,
  session: null,
  request: null,
})

const waiting: InboxItem = {
  ...stopped(1),
  kind: 'session',
  ticket: null,
  session: { session_id: 's1', cwd: '/work/sample', action: { tool: 'Bash', summary: 'ls' } },
}

const asked: InboxItem = {
  ...stopped(2),
  kind: 'question',
  question: { document: 'brd.md', index: 0, text: 'Which size?', choices: [], several: false },
}

function listing(sections: Partial<Record<(typeof SECTIONS)[number], InboxItem[]>>): Inbox {
  const empty = Object.fromEntries(SECTIONS.map((s) => [s, [] as InboxItem[]]))
  const count = Object.values(sections).reduce((sum, items) => sum + items.length, 0)
  return { ...empty, ...sections, count, latest: '', next_up: null, push: null } as Inbox
}

async function open(inbox: Inbox, address = '/inbox') {
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify(inbox), { headers: { 'Content-Type': 'application/json' } }),
      ),
    ),
  )
  const router = memoryRouter()
  await router.push(address)
  const page = mount(InboxPage, {
    attachTo: document.body,
    global: {
      provide: { [ATTENTION as symbol]: { refresh: () => Promise.resolve() } },
      plugins: [router],
      stubs: { RouterLink: true, teleport: true },
    },
  })
  await flushPromises()
  return { page, router }
}

const rows = (page: ReturnType<typeof mount>) =>
  page.findAll(
    'section[aria-labelledby="inbox-stopped"] [data-slot="section-content"] > [data-slot="item-group"] > [role="listitem"]',
  )

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

describe('paging the inbox', () => {
  const fiftyOne = Array.from({ length: 51 }, (_, n) => stopped(n + 1))

  test('a_section_draws_fifty_rows_and_pages_the_rest', async () => {
    const { page } = await open(listing({ stopped: fiftyOne }))

    expect(rows(page)).toHaveLength(50)
    expect(page.get('[data-testid="page-range"]').text()).toBe('1 to 50 of 51')
    expect(page.get('#inbox-stopped').text()).toContain('51')
  })

  test('the_second_page_of_a_section_holds_the_row_after_the_fiftieth', async () => {
    const { page } = await open(listing({ stopped: fiftyOne }), '/inbox?stopped_page=2')

    const opened = rows(page).flatMap((row) => row.findAll('router-link-stub'))

    expect(opened.map((link) => link.attributes('to'))).toContain('/tickets/sample/CF-51')
    expect(rows(page)).toHaveLength(1)
    expect(page.get('[data-testid="page-range"]').text()).toBe('51 to 51 of 51')
  })

  test('a_push_link_to_a_row_on_a_later_page_opens_that_page', async () => {
    const { page, router } = await open(
      listing({ stopped: fiftyOne }),
      '/inbox#stopped-sample-CF-51',
    )

    expect(router.currentRoute.value.query).toEqual({ stopped_page: '2' })
    expect(router.currentRoute.value.hash).toBe('#stopped-sample-CF-51')
    expect(page.find('#stopped-sample-CF-51').exists()).toBe(true)
  })

  test('a_push_link_to_a_question_on_a_later_page_opens_that_page', async () => {
    const many = Array.from({ length: 51 }, (_, n) => ({
      ...asked,
      ticket: { repository: 'sample', id: `CF-${String(n + 1)}`, title: 'T' },
    }))
    const { page, router } = await open(
      listing({ questions: many }),
      '/inbox#question-sample-CF-51-brd.md-0',
    )

    expect(router.currentRoute.value.query).toEqual({ questions_page: '2' })
    expect(page.find('[id="question-sample-CF-51-brd.md-0"]').exists()).toBe(true)
  })

  test('the_primary_button_stays_on_the_row_next_up_names_on_a_later_page', async () => {
    const inbox = { ...listing({ stopped: fiftyOne }), next_up: { section: 'stopped', index: 50 } }
    const { page } = await open(inbox as Inbox, '/inbox?stopped_page=2')

    expect(page.get('section[aria-labelledby="inbox-stopped"]').findAll(PRIMARY)).toHaveLength(1)
  })

  test('a_section_that_fits_one_page_has_no_page_control', async () => {
    const { page } = await open(listing({ stopped: fiftyOne.slice(0, 50) }))

    expect(page.find('nav[aria-label="Pages of stopped agents"]').exists()).toBe(false)
  })
})

describe('what the inbox leads with', () => {
  const headings = (page: ReturnType<typeof mount>) =>
    page.findAll('h2').map((h) => h.text().replace(/[\s,]*\d+$/, ''))

  test('what_needs_an_act_comes_before_the_sessions_it_cannot_act_on', async () => {
    const { page } = await open(listing({ sessions: [waiting], questions: [asked] }))

    expect(headings(page)).toEqual([
      'Act now',
      'Questions',
      'For your information',
      'Waiting sessions',
    ])
  })

  test('with_only_sessions_waiting_no_group_is_titled', async () => {
    const { page } = await open(listing({ sessions: [waiting] }))

    expect(headings(page)).toEqual(['Waiting sessions'])
  })

  test('with_nothing_for_information_no_group_is_titled', async () => {
    const { page } = await open(listing({ questions: [asked] }))

    expect(headings(page)).toEqual(['Questions'])
  })
})

describe('desktop notifications', () => {
  const permission = (state: NotificationPermission) =>
    vi.stubGlobal('Notification', { permission: state, requestPermission: vi.fn() })

  test('a_browser_that_blocks_them_leaves_no_warning_on_the_page', async () => {
    permission('denied')
    const { page } = await open(listing({ questions: [asked] }))

    expect(page.text()).not.toContain('Blocked by the browser')
    expect(page.find('#notify-toggle').exists()).toBe(false)
  })

  test('a_browser_that_allows_them_offers_the_switch', async () => {
    permission('granted')
    const { page } = await open(listing({ questions: [asked] }))

    expect(page.get('#notify-toggle').attributes('role')).toBe('switch')
  })
})

describe('a stopped agent', () => {
  // The row leads with its ticket; why it stopped is the muted line under it, not a bold title.
  test('a_stopped_row_leads_with_its_ticket_and_mutes_the_reason', async () => {
    const { page } = await open(listing({ stopped: [stopped(1)] }))
    const row = rows(page)[0]
    const reason = row?.findAll('p').find((p) => p.text().includes('ran out of turns'))

    expect(reason?.classes()).toContain('text-muted-foreground')
    expect(reason?.classes()).not.toContain('font-medium')
  })
})
