// @vitest-environment happy-dom
// CF-848: the command menu ranks tickets, pages and commands by a fuzzy match, the closest first.

import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { INLINE } from '../test/overlay'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { STAGES, type Board, type Card } from '../lib/board'
import { NEW_TICKET, panelTicket } from '../lib/openTicket'
import {
  answer,
  goldenBoard,
  memoryRouter,
  provideBoard,
  spiedBoard,
  stubFetch,
} from '../test/board'
import { present } from '../test/present'
import CommandMenu from './CommandMenu.vue'

enableAutoUnmount(afterEach)

const golden = goldenBoard()
const template = present(STAGES.flatMap((s) => golden.columns[s])[0], 'a card in the golden board')

const TITLES = [
  'The command menu finds a ticket only by an exact part of its text',
  'New child ticket opens the form with its parent set',
  'The ticket page shows its documents',
  'Archive a merged ticket',
  'Release notes name every ticket',
  'Flaky checks file a bug',
  'The inbox shows questions',
  'Agents stop on request',
  'Sessions list their runs',
  'Memory entries can be merged',
]

function boardOf(titles: string[]): Board {
  const cards: Card[] = titles.map((title, i) => ({
    ...template,
    repository: 'sample',
    id: `CF-${String(i + 1)}`,
    title,
  }))
  const columns = Object.fromEntries(STAGES.map((s) => [s, [] as Card[]])) as Board['columns']
  columns[STAGES[0]] = cards
  return { ...golden, columns }
}

async function searched(query: string, titles = TITLES): Promise<string[]> {
  // The menu loads the library when it opens and does not wait for it; the first import of the
  // module is the slow one, so it is done here, before the menu asks.
  await import('fuse.js')
  const menu = mount(CommandMenu, {
    global: { stubs: INLINE, plugins: [memoryRouter()], provide: provideBoard(boardOf(titles)) },
  })
  await (menu.vm as unknown as { open: () => Promise<void> }).open()
  await flushPromises()
  await menu.get('input[role="combobox"]').setValue(query)
  return menu.findAll('[role="option"]').map((option) => option.text())
}

// The menu reads the saved views when it opens; a test about requests stubs its own.
beforeEach(() => {
  stubFetch(() => answer([]))
})

afterEach(() => {
  document.body.innerHTML = ''
})

describe('the fuzzy command menu', () => {
  // CF-848-R1
  test('a_misspelt_query_still_finds_the_ticket', async () => {
    const rows = await searched('comand menu')

    expect(rows).toEqual([
      'CF-1 The command menu finds a ticket only by an exact part of its textsample',
    ])
  })

  // CF-848-R2
  test('words_out_of_order_still_find_the_ticket', async () => {
    const rows = await searched('set parent child new')

    expect(rows).toEqual(['CF-2 New child ticket opens the form with its parent setsample'])
  })

  // CF-848-R3
  test('the_closest_entry_comes_first_and_at_most_eight_show', async () => {
    const page = await searched('memroy')
    const narrowed = await searched('ticket merged')
    const many = await searched('ticket', [...TITLES, ...TITLES.map((t) => `${t} ticket`)])

    expect(page).toEqual(['Go to Memorypagegm', 'CF-10 Memory entries can be mergedsample'])
    expect(narrowed).toEqual(['CF-4 Archive a merged ticketsample'])
    expect(many).toHaveLength(8)
  })

  // CF-848-R4
  test('an_empty_query_lists_as_before', async () => {
    const rows = await searched('')

    expect(rows).toEqual([
      ...TITLES.slice(0, 8).map((title, i) => `CF-${String(i + 1)} ${title}sample`),
      'New ticketactionn',
      'Go to Sessionspagegs',
      'Go to Ticketspagegt',
      'Go to Inboxpagegi',
      'Go to Analyticspagega',
      'Go to Archivepagegr',
      'Go to Memorypagegm',
      'Go to Agentspagegg',
      'Go to Teampagege',
      'Agents: Connectionspage',
      'Stop every agentagent',
      'Resume agentsagent',
    ])
  })
})

// CF-1235: a page that does not show the board does not poll it, so the menu reads it as it opens.
test('opening_the_menu_reads_the_board', async () => {
  const { live, provide } = spiedBoard(boardOf(TITLES))
  const menu = mount(CommandMenu, { global: { stubs: INLINE, plugins: [memoryRouter()], provide } })
  const before = live.refresh.mock.calls.length

  await (menu.vm as unknown as { open: () => Promise<void> }).open()

  expect(before).toBe(0)
  expect(live.refresh).toHaveBeenCalledTimes(1)
})

// CF-1272: the entries that start the common actions by name.
const SAMPLE = { repository: 'sample', id: 'CF-1' }

interface Opened {
  menu: ReturnType<typeof mount>
  router: ReturnType<typeof memoryRouter>
  newTicket: ReturnType<typeof vi.fn>
}

/** The menu at `address`, the board holding one ticket `CF-1` with `card` set on it. */
async function menuAt(address: string, card: Partial<Card> = {}): Promise<Opened> {
  const board = boardOf(['A ticket'])
  const first = present(board.columns.spec[0], 'the ticket')
  board.columns.spec = [{ ...first, stage: 'spec', runs: [], archived: false, ...card }]
  const router = memoryRouter([
    { path: '/tickets/:repository/:id', component: { template: '<div />' } },
    { path: '/sessions/:id', component: { template: '<div />' } },
    { path: '/:rest(.*)*', component: { template: '<div />' } },
  ])
  await router.push(address)
  const newTicket = vi.fn()
  const menu = mount(CommandMenu, {
    global: {
      stubs: INLINE,
      plugins: [router],
      provide: { ...provideBoard(board), [NEW_TICKET as symbol]: newTicket },
    },
  })
  await (menu.vm as unknown as { open: () => Promise<void> }).open()
  await flushPromises()
  return { menu, router, newTicket }
}

const rows = (menu: Opened['menu']) =>
  menu.findAll('[role="option"]').map((option) => option.text())
const row = (menu: Opened['menu'], label: string) =>
  present(
    menu.findAll('[role="option"]').find((option) => option.text().startsWith(label)),
    label,
  )

afterEach(() => {
  panelTicket.value = null
  vi.unstubAllGlobals()
})

describe('the entries for the common actions', () => {
  // CF-1272-R1
  test('new_ticket_opens_the_form_where_the_person_is_and_shows_its_key', async () => {
    const { menu, router, newTicket } = await menuAt('/memory')

    expect(row(menu, 'New ticket').text()).toBe('New ticketactionn')
    await row(menu, 'New ticket').trigger('click')
    await flushPromises()

    expect([newTicket.mock.calls.length, router.currentRoute.value.fullPath]).toEqual([
      1,
      '/memory',
    ])
  })

  // CF-1272-R2
  test('start_agent_and_archive_show_only_while_a_ticket_is_open', async () => {
    const names = (o: Opened) => rows(o.menu).filter((r) => /^(Start agent|Archive)/.test(r))
    const away = names(await menuAt('/memory'))
    const onPage = names(await menuAt('/tickets/sample/CF-1'))
    panelTicket.value = SAMPLE
    const inPanel = names(await menuAt('/memory'))

    expect([away, onPage, inPanel]).toEqual([
      [],
      ['Start agentCF-1s', 'ArchiveCF-1'],
      ['Start agentCF-1s', 'ArchiveCF-1'],
    ])
  })

  // CF-1272-R3
  test('start_agent_shows_only_in_a_column_an_agent_works_in_with_none_running', async () => {
    const cases: [Partial<Card>, number][] = [
      [{ stage: 'review' }, 0],
      [{ runs: [{ id: 'r1' } as unknown as Card['runs'][number]] }, 0],
      [{ stage: 'build' }, 1],
    ]

    for (const [card, count] of cases) {
      const { menu } = await menuAt('/tickets/sample/CF-1', card)
      expect(rows(menu).filter((label) => label.startsWith('Start agent'))).toHaveLength(count)
      menu.unmount()
    }
  })

  // CF-1272-R2
  test('a_session_page_is_not_an_open_ticket', async () => {
    const { menu } = await menuAt('/sessions/CF-1')

    expect(rows(menu).filter((r) => /^(Start agent|Archive)/.test(r))).toEqual([])
  })

  // CF-1272-R4
  test('archive_is_not_offered_for_an_archived_ticket', async () => {
    const { menu } = await menuAt('/tickets/sample/CF-1', { archived: true })

    expect(rows(menu).filter((r) => r.startsWith('Archive'))).toEqual([])
  })

  // CF-1272-R5
  test('start_agent_sends_the_status_buttons_request_for_the_open_ticket', async () => {
    const sent = stubFetch((url) =>
      answer(url === '/api/views' ? [] : { notice: 'Started', undo: null }),
    )
    const { menu } = await menuAt('/tickets/sample/CF-1')

    await row(menu, 'Start agent').trigger('click')
    await flushPromises()

    expect(sent).toEqual([
      { method: 'GET', url: '/api/views', body: undefined },
      {
        method: 'POST',
        url: '/api/tickets/sample/CF-1/runs',
        body: { permissions: 'bypassPermissions', loop: true },
      },
    ])
  })

  // CF-1272-R6
  test('archive_sends_the_archive_change_for_the_open_ticket_without_asking', async () => {
    const sent = stubFetch((url) =>
      answer(url === '/api/views' ? [] : { notice: 'Archived', undo: null }),
    )
    panelTicket.value = SAMPLE
    const { menu } = await menuAt('/memory')

    await row(menu, 'Archive').trigger('click')
    await flushPromises()

    expect(sent).toEqual([
      { method: 'GET', url: '/api/views', body: undefined },
      { method: 'PATCH', url: '/api/tickets/sample/CF-1', body: { archived: 'true' } },
    ])
  })

  // CF-1272-R7
  test('agents_connections_opens_the_connections_tab', async () => {
    const { menu, router } = await menuAt('/tickets')

    await row(menu, 'Agents: Connections').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.fullPath).toBe('/agents?tab=connections')
  })

  // CF-1272-R8
  test('a_page_is_entered_only_after_the_menus_history_entry_is_popped', async () => {
    // A browser traverses history after the call returns; a push made before that is undone by it.
    // The traversal here waits for the test.
    const traverse = history.back.bind(history)
    const waiting: { traverse?: () => void } = {}
    vi.spyOn(history, 'back').mockImplementation(() => {
      waiting.traverse = traverse
    })
    const { menu, router } = await menuAt('/tickets')

    await row(menu, 'Go to Inbox').trigger('click')
    await flushPromises()
    const during = router.currentRoute.value.fullPath
    present(waiting.traverse, 'the menu popping its entry')()
    await vi.waitFor(() => {
      expect(router.currentRoute.value.fullPath).toBe('/inbox')
    })
    vi.restoreAllMocks()

    expect(during).toBe('/tickets')
  })
})

// An archived or released ticket is found from the menu too: under Archived, after the live
// entries, each saying how it left the board, from the Archive page's own search.
describe('archived tickets in the menu', () => {
  const ROW = { repository: 'shop-api', type: 'feature', archived_at: 0 }
  const ARCHIVE = {
    rows: [
      {
        ...ROW,
        id: 'CF-1',
        title: 'Checkout refunds partial orders',
        stage: 'released',
        archived: false,
        release: '1.3.0',
      },
      { ...ROW, id: 'CF-4', title: 'Refunds by hand', stage: 'build', archived: true, release: '' },
    ],
    archived_count: 2,
    sort: 'archived',
    dir: 'desc',
    total: 2,
    page: 1,
    size: 8,
  }

  async function typed(query: string) {
    const sent = stubFetch((url) => answer(url.startsWith('/api/archive') ? ARCHIVE : []))
    await import('fuse.js')
    const menu = mount(CommandMenu, {
      global: { stubs: INLINE, plugins: [memoryRouter()], provide: provideBoard(boardOf(TITLES)) },
    })
    await (menu.vm as unknown as { open: () => Promise<void> }).open()
    await menu.get('input[role="combobox"]').setValue(query)
    await new Promise((resolve) => setTimeout(resolve, 400))
    await flushPromises()
    return { menu, sent }
  }

  test('an_archived_ticket_is_found_under_archived_with_how_it_left', async () => {
    const { menu } = await typed('refunds')
    const group = menu.find('[data-archived]')

    expect({
      heading: group.exists() && group.text().startsWith('Archived'),
      rows: group.findAll('[role="option"]').map((option) => option.text()),
    }).toEqual({
      heading: true,
      rows: ['CF-1 Checkout refunds partial ordersReleased 1.3.0', 'CF-4 Refunds by handArchived'],
    })
  })

  test('a_query_under_two_characters_does_not_search_the_archive', async () => {
    const { menu, sent } = await typed('r')

    expect(sent.filter((s) => s.url.startsWith('/api/archive'))).toEqual([])
    expect(menu.find('[data-archived]').exists()).toBe(false)
  })
})
