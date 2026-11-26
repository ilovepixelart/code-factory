import { flushPromises, mount } from '@vue/test-utils'
import { chosen, clearSelection } from '@/lib/selection'
import { expect, test } from 'vitest'
import type { Card } from '@/lib/board'
import { goldenBoard, memoryRouter, provideBoard } from '../../support/board'
import { INLINE, menuItem, openMenu } from '../../support/overlay'
import { present } from '../../support/present'
import TicketList from '@/components/TicketList.vue'

const board = goldenBoard()
const base = present(board.columns.spec[0], 'a card')

function list(rows: Card[]) {
  return mount(TicketList, {
    props: { rows, sort: 'id', direction: 'asc', sortUrl: () => '/tickets/list' },
    global: { plugins: [memoryRouter()], provide: provideBoard(board) },
  })
}
const headers = (view: ReturnType<typeof list>) => view.findAll('th').map((th) => th.text())

// A column is named as a person reads it, and an empty priority says so rather than leave a hole.
test('the_id_column_reads_ID_and_no_priority_reads_none', () => {
  const view = list([
    { ...base, id: 'CF-1', priority: '' },
    { ...base, id: 'CF-2', priority: 'high' },
  ])
  const names = headers(view).map((h) => h.replace(/[↑↓]/g, ''))
  const priority = names.indexOf('Priority')
  const cells = view.findAll('tbody tr').map((tr) => tr.findAll('td')[priority]?.text())

  expect(names).toContain('ID')
  expect(names).not.toContain('Id')
  expect(cells).toEqual(['none', 'high'])
})

// CF-1079-R1: two rows of one repository and no assignee: neither column shows, nor its cells.
test('a_column_of_nothing_is_left_out', () => {
  const view = list([
    { ...base, id: 'CF-1', assignee: '', repository: 'code-factory' },
    { ...base, id: 'CF-2', assignee: '', repository: 'code-factory' },
  ])

  expect(headers(view)).not.toContain('Assignee')
  expect(headers(view)).not.toContain('Repository')
  expect(view.find('tbody tr').findAll('td')).toHaveLength(headers(view).length)
})

// CF-1079-R1: rows of two repositories, one assigned: both columns show.
test('a_column_that_differs_stays', () => {
  const view = list([
    { ...base, id: 'CF-1', assignee: 'alex', repository: 'code-factory' },
    { ...base, id: 'API-1', assignee: '', repository: 'api' },
  ])

  expect(headers(view)).toContain('Assignee')
  expect(headers(view)).toContain('Repository')
  expect(view.find('tbody tr').findAll('td')).toHaveLength(headers(view).length)
})

// CF-1079-R2: a label's dot on the list is the colour the board's composable gives it.
// A row's box ticks its card into the bulk selection the board's cards share, so the bulk bar acts
// on the same set; the header box ticks every row of the page.
test('a_ticked_row_joins_the_bulk_selection', async () => {
  clearSelection()
  const view = list([
    { ...base, id: 'CF-1', repository: 'code-factory' },
    { ...base, id: 'CF-2', repository: 'code-factory' },
  ])
  const boxes = () => view.findAll('[role="checkbox"]')
  await boxes()[2]?.trigger('click')
  await flushPromises()
  expect([...chosen]).toEqual(['code-factory/CF-2'])

  await boxes()[0]?.trigger('click')
  await flushPromises()
  expect([...chosen].sort()).toEqual(['code-factory/CF-1', 'code-factory/CF-2'])
  clearSelection()
})

test('a_label_has_one_colour_everywhere', () => {
  const labels = ['agents', 'ui']
  const view = mount(TicketList, {
    props: {
      rows: [{ ...base, labels }],
      sort: 'id',
      direction: 'asc',
      sortUrl: () => '/tickets/list',
    },
    global: {
      plugins: [memoryRouter()],
      provide: provideBoard({ ...board, options: { ...board.options, label: labels } }),
    },
  })

  const dots = view
    .findAll('[data-slot="badge"] > [aria-hidden="true"]')
    .map((s) => s.classes().find((c) => c.startsWith('bg-chart-')))
  expect(dots).toEqual(['bg-chart-1', 'bg-chart-2'])
})

// Eight columns are more than a person needs at once: the Columns menu hides the ones they do not
// read, the ID and title always stay, and the choice holds for the next visit in this browser.
test('the_columns_a_person_hides_stay_hidden_and_id_and_title_cannot_hide', async () => {
  localStorage.removeItem('codeFactoryListColumns')
  const rows = [{ ...base, id: 'CF-1' }]
  const mounted = () =>
    mount(TicketList, {
      props: { rows, sort: 'id', direction: 'asc', sortUrl: () => '/tickets/list' },
      global: { plugins: [memoryRouter()], provide: provideBoard(board), stubs: INLINE },
    })
  const first = mounted()
  await openMenu(first, '[data-slot="dropdown-menu-trigger"]')
  const hideable = first.findAll('[role="menuitemcheckbox"]').map((item) => item.text())
  await menuItem(first, 'Type').trigger('click')
  await flushPromises()
  first.unmount()

  expect(hideable).not.toContain('ID')
  expect(hideable).not.toContain('Title')
  expect(headers(mounted()).map((h) => h.replace(/[↑↓]/g, ''))).not.toContain('Type')
  localStorage.removeItem('codeFactoryListColumns')
})

// CF-1207: below 768 px each ticket is a card, as in the Archive, so a phone never scrolls sideways.
test('below_768_px_each_ticket_is_a_card', () => {
  const view = list([{ ...base, id: 'CF-1' }])

  expect(view.get('tbody tr').classes()).toContain('max-md:flex')
  expect(view.get('thead').classes()).toContain('max-md:hidden')
})

// A stage reads as its glyph and its word, and the delivery state sits beside them on the same
// line as a badge rather than on a second line under the stage.
test('the_stage_cell_is_glyph_word_and_delivery_badge_on_one_line', () => {
  const view = list([{ ...base, id: 'CF-1', stage: 'build', open_questions: 1, archived: false }])
  const names = headers(view).map((h) => h.replace(/[↑↓]/g, '').trim())
  const cell = view.find('tbody tr').findAll('td')[names.indexOf('Stage')]
  const line = cell?.get('[data-stage-cell]')

  expect({
    glyph: line?.find('svg[data-shape="half"]').exists(),
    word: line?.text().startsWith('Build'),
    badge: line?.find('[data-slot="badge"]').text(),
    oneLine: line?.classes().includes('whitespace-nowrap'),
  }).toEqual({ glyph: true, word: true, badge: 'Waiting for an answer', oneLine: true })
})
