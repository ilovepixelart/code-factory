// docs/ui.md (The kanban): a column the person folded keeps that choice until its card count
// crosses zero; filtering the board changes what is drawn, not what the column holds.

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { STAGES, type Board } from '@/lib/board'
import { BOARD } from '@/lib/live'
import { answer, goldenBoard, memoryRouter, provideBoard, stubFetch } from '../../support/board'
import TicketsPage from '@/pages/TicketsPage.vue'

const CHOICES = 'codeFactoryColumns'
const COUNTS = 'codeFactoryColumnCounts'

async function pageFor(board: Board) {
  document.body.innerHTML = '<div id="header-controls"></div><div id="app"></div>'
  const router = memoryRouter([
    { path: '/tickets', component: TicketsPage, meta: { list: false } },
    { path: '/tickets/list', component: TicketsPage, meta: { list: true } },
  ])
  await router.push('/tickets')
  const provide = provideBoard(board)
  const page = mount(TicketsPage, {
    attachTo: '#app',
    global: {
      plugins: [router],
      provide,
      stubs: Object.fromEntries(
        ['BoardColumn', 'TicketList', 'TicketPanel', 'NewTicket', 'BulkBar', 'HaltNotice'].map(
          (name) => [name, true],
        ),
      ),
    },
  })
  await flushPromises()
  const live = provide[BOARD as symbol]
  if (!live) throw new Error('the live board is not provided')
  return { page, live }
}

const choices = (): unknown => JSON.parse(localStorage.getItem(CHOICES) ?? 'null')

beforeEach(() => {
  const board = goldenBoard()
  const counts = Object.fromEntries(STAGES.map((s) => [s, String(board.columns[s].length)]))
  stubFetch(() => answer({}))
  localStorage.setItem(CHOICES, JSON.stringify({ spec: true }))
  localStorage.setItem(COUNTS, JSON.stringify(counts))
})

afterEach(() => {
  document.body.innerHTML = ''
  localStorage.clear()
  vi.unstubAllGlobals()
})

test('a_filter_matching_no_card_of_a_column_keeps_its_fold', async () => {
  const board = goldenBoard()
  expect(board.columns.spec.length).toBeGreaterThan(0)
  const { page } = await pageFor(board)

  const box = document.querySelector<HTMLInputElement>('input[aria-label="Filter cards"]')
  if (!box) throw new Error('the filter box is missing')
  box.value = 'zzz-matches-no-card'
  box.dispatchEvent(new Event('input'))
  await flushPromises()

  expect(choices()).toEqual({ spec: true })
  page.unmount()
})

test('a_column_whose_cards_all_leave_the_board_drops_its_fold', async () => {
  const board = goldenBoard()
  const { page, live } = await pageFor(board)

  live.board.value = { ...board, columns: { ...board.columns, spec: [] } }
  await flushPromises()

  expect(choices()).toEqual({})
  page.unmount()
})
