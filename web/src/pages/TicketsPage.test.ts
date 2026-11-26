// @vitest-environment happy-dom
// CF-311: the filter box's text lives in the address: every link the board builds keeps it,
// and the box follows the address when it changes (docs/ui.md).

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, test } from 'vitest'
import { answer, goldenBoard, memoryRouter, provideBoard, stubFetch } from '../test/board'
import * as selection from '../lib/selection'
import { present } from '../test/present'
import TicketsPage from './TicketsPage.vue'

const board = goldenBoard()
const noTickets = {
  ...board,
  columns: { spec: [], build: [], review: [], merged: [] },
}

async function pageAt(
  address: string,
  real: string[] = [],
  held: typeof board | null = board,
  failed = '',
) {
  document.body.innerHTML = '<div id="header-controls"></div><div id="app"></div>'
  const router = memoryRouter([
    { path: '/tickets', component: TicketsPage, meta: { list: false } },
    { path: '/tickets/list', component: TicketsPage, meta: { list: true } },
  ])
  await router.push(address)
  const page = mount(TicketsPage, {
    attachTo: '#app',
    global: {
      plugins: [router],
      provide: provideBoard(held, 'live', failed),
      stubs: Object.fromEntries(
        ['BoardColumn', 'TicketList', 'TicketPanel', 'NewTicket', 'BulkBar', 'HaltNotice']
          .filter((name) => !real.includes(name))
          .map((name) => [name, true]),
      ),
    },
  })
  await flushPromises()
  return { page, router }
}

const links = (): string[] =>
  [...document.querySelectorAll('a')].map((a) => a.getAttribute('href') ?? '')

/** Opens the header's menus (Lanes, Filter) and every submenu: their links render only while open. */
async function openMenus(): Promise<void> {
  for (const trigger of document.querySelectorAll<HTMLElement>(
    '#header-controls [aria-haspopup="menu"]',
  )) {
    trigger.click()
    await flushPromises()
  }
  for (const sub of document.querySelectorAll<HTMLElement>(
    '[data-slot="dropdown-menu-sub-trigger"]',
  )) {
    sub.click()
    await flushPromises()
  }
}

// The page reads the saved views.
beforeEach(() => {
  stubFetch(() => answer([]))
})

afterEach(() => {
  document.body.innerHTML = ''
})

describe('the filter box in the address', () => {
  test('every_board_link_keeps_the_filter_text', async () => {
    const list = await pageAt('/tickets/list?q=search+me&type=bug', ['TicketList'])
    await openMenus()
    const fromList = links().filter((href) => href.startsWith('/tickets'))
    list.page.unmount()
    const { page } = await pageAt('/tickets?q=search+me&type=bug')
    await openMenus()
    const built = [...fromList, ...links().filter((href) => href.startsWith('/tickets'))]

    expect(built.length).toBeGreaterThan(5)
    expect(built.filter((href) => !href.includes('q=search+me'))).toEqual([])
    page.unmount()
  })

  test('the_filter_box_follows_the_address', async () => {
    const { page, router } = await pageAt('/tickets?q=first')

    await router.push('/tickets?q=second')
    await flushPromises()
    const box = document.querySelector<HTMLInputElement>('input[aria-label="Filter cards"]')

    expect(box?.value).toBe('second')
    page.unmount()
  })
})

// CF-338: docs/ui.md (The kanban), filter values are links to the filtered address.
describe('the filter menu', () => {
  const valueLinks = () =>
    Object.fromEntries(
      [...document.querySelectorAll('[aria-label="Filters"] [role="menu"] a')].map((a) => [
        a.textContent.trim(),
        a.getAttribute('href'),
      ]),
    )

  test('filter_values_are_links_to_the_filtered_address', async () => {
    const { page } = await pageAt('/tickets?priority=high')
    const found: Record<string, string | null> = {}
    document.querySelector<HTMLElement>('#header-controls [data-filter-count]')?.click()
    await flushPromises()
    for (const sub of document.querySelectorAll<HTMLElement>(
      '[data-slot="dropdown-menu-sub-trigger"]',
    )) {
      sub.click()
      await flushPromises()
      Object.assign(found, valueLinks())
    }

    expect(found).toMatchObject({
      Bug: '/tickets?priority=high&type=bug',
      High: '/tickets',
      Low: '/tickets?priority=high&priority=low',
      second: '/tickets?priority=high&repository=second',
    })
    page.unmount()
  })
})

// The owner: the list draws no table without a ticket to put in it. With none at all it says so as
// the board does; with a filter that leaves none, it says the filter matched nothing.
describe('the list with no ticket to show', () => {
  // In a Card, at the top of the page, never centred in the board's tall area.
  const empty = () =>
    document.querySelector('[data-section] [data-slot="empty-title"]')?.textContent.trim()
  const table = () => document.querySelector('table')

  test('a_board_with_no_tickets_lists_no_table_and_shows_the_first_run', async () => {
    const { page } = await pageAt('/tickets/list', ['TicketList'], noTickets)

    expect([table(), document.querySelectorAll('[data-step]').length]).toEqual([null, 3])
    page.unmount()
  })

  test('a_filter_that_matches_nothing_lists_no_table_and_says_so', async () => {
    const { page } = await pageAt('/tickets/list?q=nothing+matches+this', ['TicketList'])

    expect([empty(), table()]).toEqual(['No tickets match the filter.', null])
    expect(
      document.querySelector('[data-section] [data-slot="empty-description"]')?.textContent.trim(),
    ).toBe('Clear a filter or try a different search.')
    page.unmount()
  })
})

describe('a board that does not answer', () => {
  test('says why with Read again instead of loading for ever', async () => {
    await pageAt('/tickets', [], null, 'boom')

    const alert = document.querySelector('[role="alert"]')
    expect(alert?.textContent).toContain('boom')
    expect(document.querySelector('[data-read-again]')).not.toBeNull()
    expect(document.body.textContent).not.toContain('Loading the board')
  })

  test('keeps the cards a previous read answered', async () => {
    await pageAt('/tickets', [], board, 'boom')

    expect(document.querySelector('[data-read-again]')).toBeNull()
    expect(document.querySelector('board-column-stub')).not.toBeNull()
  })
})

// The bulk bar floats over the page's foot: while it shows, the page leaves room for it under the
// last row, so scrolling to the end shows every row whole.
describe('room for the bulk bar', () => {
  const content = (): string =>
    document.querySelector('[data-js-tickets-content]')?.getAttribute('class') ?? ''

  afterEach(() => {
    selection.clearSelection()
  })

  test('leaves_room_under_the_rows_while_cards_are_chosen', async () => {
    const card = present(board.columns.build[0], 'a card in Build')
    selection.toggle(selection.keyOf(card.repository, card.id))
    await pageAt('/tickets/list')

    expect(document.querySelector('bulk-bar-stub')).not.toBeNull()
    expect(content()).toMatch(/\bpb-\d+\b/)
  })

  test('leaves_no_room_without_a_choice', async () => {
    await pageAt('/tickets/list')

    expect(document.querySelector('bulk-bar-stub')).toBeNull()
    expect(content()).not.toMatch(/\bpb-\d+\b/)
  })
})

// The audit's first run: an empty board leads to a working one in three steps, each ticked once
// done, instead of only saying there are no tickets.
describe('the first run checklist', () => {
  const steps = () =>
    [...document.querySelectorAll<HTMLElement>('[data-step]')].map((step) => [
      step.dataset.step,
      step.dataset.done,
    ])

  function world(repositories: string[], connections: number, refusal = '') {
    let tracked = [...repositories]
    return stubFetch((url, init) => {
      if (url === '/api/repositories' && init?.method === 'POST') {
        if (refusal) return answer({ detail: refusal }, 400)
        tracked = ['shop']
        return answer({ name: 'shop', path: '/src/shop' }, 201)
      }
      if (url === '/api/repositories') return answer(tracked)
      if (url === '/api/connections') {
        const listed = Array.from({ length: connections }, (_, at) => ({ name: `c${String(at)}` }))
        return answer({ connections: listed, kinds: [], problem: '' })
      }
      return answer([])
    })
  }

  test('an_empty_board_lists_the_three_steps_and_ticks_none', async () => {
    world([], 0)
    const { page } = await pageAt('/tickets', [], noTickets)

    expect(steps()).toEqual([
      ['track', 'false'],
      ['connect', 'false'],
      ['file', 'false'],
    ])
    expect(page.get('[aria-current="step"]').attributes('data-step')).toBe('track')
    expect(page.get('[role="progressbar"]').attributes('aria-valuetext')).toBe(
      '0 of 3 steps complete',
    )
    page.unmount()
  })

  test('a_step_already_done_is_ticked', async () => {
    world(['shop'], 1)
    const { page } = await pageAt('/tickets', [], noTickets)

    expect(steps()).toEqual([
      ['track', 'true'],
      ['connect', 'true'],
      ['file', 'false'],
    ])
    page.unmount()
  })

  test('tracking_a_folder_sends_its_path_and_ticks_the_step', async () => {
    const sent = world([], 0)
    const { page } = await pageAt('/tickets', [], noTickets)

    await page.get('[data-step="track"] input').setValue('/src/shop')
    await page.get('[data-step="track"] form').trigger('submit')
    await flushPromises()

    expect(sent.filter((s) => s.method === 'POST')).toEqual([
      { method: 'POST', url: '/api/repositories', body: { path: '/src/shop' } },
    ])
    expect(steps()[0]).toEqual(['track', 'true'])
    expect(page.get('[aria-current="step"]').attributes('data-step')).toBe('connect')
    expect(page.get('[role="progressbar"]').attributes('aria-valuetext')).toBe(
      '1 of 3 steps complete',
    )
    page.unmount()
  })

  test('a_refused_folder_says_why_under_the_field', async () => {
    world([], 0, '/src/shop is not a git repository: run git init there')
    const { page } = await pageAt('/tickets', [], noTickets)

    await page.get('[data-step="track"] input').setValue('/src/shop')
    await page.get('[data-step="track"] form').trigger('submit')
    await flushPromises()

    expect(page.get('[data-step="track"] [data-slot="field-error"]').text()).toBe(
      '/src/shop is not a git repository: run git init there',
    )
    expect(steps()[0]).toEqual(['track', 'false'])
    page.unmount()
  })
})
