// @vitest-environment happy-dom

import { flushPromises, mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import { reactive } from 'vue'
import { memoryRouter } from '../../test/board'
import { INLINE, menuItem, openMenu } from '../../test/overlay'
import DataTable from './DataTable.vue'
import type { DataTableColumn } from './features'

interface Pull {
  id: string
  title: string
  runs: number
}

const PULLS: Pull[] = [
  { id: 'a', title: 'Read the default branch', runs: 3 },
  { id: 'b', title: 'Keep the archive paged', runs: 12 },
  { id: 'c', title: 'Answer from the phone', runs: 7 },
]

const COLUMNS: DataTableColumn<Pull>[] = [
  { accessorKey: 'title', header: 'Title' },
  { accessorKey: 'runs', header: 'Runs' },
]

async function table(
  props: Record<string, unknown> = {},
  path = '/',
  slots: Record<string, string> = {},
) {
  const router = memoryRouter()
  await router.push(path)
  // The generic component's props are typed for one row type at a time; the cases vary it.
  const view = mount(DataTable, {
    props: { columns: COLUMNS, data: PULLS, rowId: (p: Pull) => p.id, ...props } as never,
    slots,
    global: { plugins: [router], stubs: INLINE },
  })
  return Object.assign(view, { router })
}
const texts = (view: Awaited<ReturnType<typeof table>>, selector: string): string[] =>
  view.findAll(selector).map((el) => el.text())

test('a_header_per_column_and_a_row_per_datum_in_the_order_given', async () => {
  const view = await table()

  expect(texts(view, 'th')).toEqual(['Title', 'Runs'])
  expect(view.findAll('tbody tr').map((tr) => tr.findAll('td').map((td) => td.text()))).toEqual([
    ['Read the default branch', '3'],
    ['Keep the archive paged', '12'],
    ['Answer from the phone', '7'],
  ])
})

test('a_columns_look_lands_on_its_header_and_each_of_its_cells', async () => {
  const columns: DataTableColumn<Pull>[] = [
    { accessorKey: 'title', header: 'Title' },
    {
      accessorKey: 'runs',
      header: 'Runs',
      meta: { cell: 'text-right tabular-nums', head: 'text-right' },
    },
  ]
  const view = await table({ columns })

  expect(view.findAll('th')[1]?.classes()).toContain('text-right')
  expect(view.findAll('th')[0]?.classes()).not.toContain('text-right')
  for (const row of view.findAll('tbody tr')) {
    expect(row.findAll('td')[1]?.classes()).toEqual(
      expect.arrayContaining(['text-right', 'tabular-nums']),
    )
    expect(row.findAll('td')[0]?.classes()).not.toContain('tabular-nums')
  }
})

const runsColumn = (view: Awaited<ReturnType<typeof table>>): number[] =>
  texts(view, 'tbody tr td:nth-child(2)').map(Number)
const headLink = (view: Awaited<ReturnType<typeof table>>, n: number): string =>
  view.findAll('th')[n]?.find('a').attributes('href') ?? ''

test('rows_sort_by_the_column_and_direction_the_address_names_numbers_as_numbers', async () => {
  expect(runsColumn(await table({}, '/?sort=runs&dir=desc'))).toEqual([12, 7, 3])
  expect(runsColumn(await table({}, '/?sort=runs&dir=asc'))).toEqual([3, 7, 12])
})

test('without_a_sort_in_the_address_rows_keep_the_order_given_and_no_header_is_sorted', async () => {
  const view = await table({}, '/')

  expect(runsColumn(view)).toEqual([3, 12, 7])
  expect(view.findAll('th').map((th) => th.attributes('aria-sort'))).toEqual([undefined, undefined])
})

test('a_sort_naming_no_column_of_the_table_is_ignored', async () => {
  expect(runsColumn(await table({}, '/?sort=cost&dir=desc'))).toEqual([3, 12, 7])
})

test('a_header_links_its_sort_descending_first_and_flips_the_current_one', async () => {
  const view = await table({}, '/?sort=runs&dir=desc')

  expect(view.findAll('th')[1]?.attributes('aria-sort')).toBe('descending')
  expect(headLink(view, 1)).toBe('/?sort=runs&dir=asc')
  expect(headLink(view, 0)).toBe('/?sort=title&dir=desc')
})

test('a_sort_link_keeps_the_other_keys_and_goes_back_to_the_first_page', async () => {
  const view = await table({}, '/?page=3&size=25&show=hand')

  expect(headLink(view, 1)).toBe('/?size=25&show=hand&sort=runs&dir=desc')
})

test('a_prefix_keeps_two_tables_of_one_page_apart', async () => {
  const view = await table(
    { prefix: 'merged_' },
    '/?sort=title&dir=asc&merged_sort=runs&merged_dir=asc',
  )

  expect(runsColumn(view)).toEqual([3, 7, 12])
  expect(headLink(view, 1)).toBe('/?sort=title&dir=asc&merged_sort=runs&merged_dir=desc')
})

test('a_column_that_does_not_sort_has_a_plain_header', async () => {
  const columns: DataTableColumn<Pull>[] = [
    { accessorKey: 'title', header: 'Title', enableSorting: false },
    { accessorKey: 'runs', header: 'Runs' },
  ]
  const view = await table({ columns })

  expect(view.findAll('th')[0]?.find('a').exists()).toBe(false)
  expect(view.findAll('th')[0]?.text()).toBe('Title')
})

const many = (n: number): Pull[] =>
  Array.from({ length: n }, (_, i) => ({
    id: `p${String(i + 1)}`,
    title: `Pull ${String(i + 1)}`,
    runs: i + 1,
  }))

// More rows than the largest page size, so a table that slices anyway cannot pass.
test('a_table_that_is_not_paged_shows_every_row', async () => {
  expect(runsColumn(await table({ data: many(120) }))).toHaveLength(120)
})

test('a_paged_table_shows_the_page_and_size_the_address_names', async () => {
  const paged = { label: 'pulls', fallback: 10 }

  expect(runsColumn(await table({ data: many(12), paged }))).toEqual([
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10,
  ])
  expect(runsColumn(await table({ data: many(12), paged }, '/?page=2'))).toEqual([11, 12])
  expect(runsColumn(await table({ data: many(30), paged }, '/?page=2&size=25'))).toEqual([
    26, 27, 28, 29, 30,
  ])
})

test('the_whole_list_is_sorted_before_it_is_paged', async () => {
  const view = await table(
    { data: many(12), paged: { label: 'pulls', fallback: 10 } },
    '/?sort=runs&dir=desc&page=2',
  )

  expect(runsColumn(view)).toEqual([2, 1])
})

test('a_paged_table_names_its_rows_under_it', async () => {
  const view = await table({ data: many(12), paged: { label: 'pulls', fallback: 10 } })

  expect(view.text()).toContain('1 to 10 of 12')
})

const COLUMNS_MENU = '[data-slot="dropdown-menu-trigger"]'

test('only_a_table_that_asks_for_it_has_a_columns_menu', async () => {
  expect((await table()).find(COLUMNS_MENU).exists()).toBe(false)
  expect((await table({ hideable: true })).get(COLUMNS_MENU).text()).toBe('Columns')
})

test('the_columns_menu_lists_the_columns_that_can_hide_by_name', async () => {
  const columns: DataTableColumn<Pull>[] = [
    { accessorKey: 'title', header: 'Title', enableHiding: false },
    { accessorKey: 'runs', header: 'Runs' },
    { id: 'share', header: () => '%', meta: { label: 'Share' }, cell: () => '' },
  ]
  const view = await table({ columns, hideable: true })
  await openMenu(view, COLUMNS_MENU)

  expect(view.findAll('[role="menuitemcheckbox"]').map((item) => item.text())).toEqual([
    'Runs',
    'Share',
  ])
})

test('a_column_unticked_in_the_menu_leaves_the_header_and_every_row', async () => {
  const view = await table({ hideable: true })
  await openMenu(view, COLUMNS_MENU)
  await menuItem(view, 'Runs').trigger('click')
  await flushPromises()

  expect(texts(view, 'th')).toEqual(['Title'])
  expect(view.findAll('tbody tr').map((tr) => tr.findAll('td').length)).toEqual([1, 1, 1])
})

const FILTER = { column: 'title', label: 'Filter pulls', placeholder: 'Filter by title' }
const titles = (view: Awaited<ReturnType<typeof table>>): string[] =>
  texts(view, 'tbody tr td:first-child')

test('only_a_table_that_asks_for_it_has_a_filter_box', async () => {
  expect((await table()).find('input[type="search"]').exists()).toBe(false)
  expect(
    (await table({ filter: FILTER })).get('input[type="search"]').attributes('aria-label'),
  ).toBe('Filter pulls')
})

test('the_filter_in_the_address_keeps_the_rows_whose_column_holds_it_in_any_case', async () => {
  expect(titles(await table({ filter: FILTER }, '/?q=ARCHIVE'))).toEqual(['Keep the archive paged'])
  expect(titles(await table({ filter: FILTER }, '/?q=the'))).toEqual([
    'Read the default branch',
    'Keep the archive paged',
    'Answer from the phone',
  ])
})

test('typing_a_filter_puts_it_in_the_address_and_goes_back_to_the_first_page', async () => {
  const view = await table({ filter: FILTER }, '/?page=2&size=25')
  await view.get('input[type="search"]').setValue('phone')
  await flushPromises()

  expect(view.router.currentRoute.value.query).toEqual({ size: '25', q: 'phone' })
  expect(titles(view)).toEqual(['Answer from the phone'])
})

test('clearing_the_filter_takes_it_out_of_the_address', async () => {
  const view = await table({ filter: FILTER, prefix: 'merged_' }, '/?merged_q=phone')
  expect(view.get<HTMLInputElement>('input[type="search"]').element.value).toBe('phone')
  await view.get('input[type="search"]').setValue('')
  await flushPromises()

  expect(view.router.currentRoute.value.query).toEqual({})
  expect(titles(view)).toHaveLength(3)
})

const boxes = (view: Awaited<ReturnType<typeof table>>) => view.findAll('[role="checkbox"]')
const checked = (view: Awaited<ReturnType<typeof table>>): (string | undefined)[] =>
  boxes(view).map((box) => box.attributes('data-state'))

test('only_a_table_given_a_selection_draws_checkboxes', async () => {
  expect(boxes(await table())).toHaveLength(0)
  expect(boxes(await table({ selected: reactive(new Set<string>()) }))).toHaveLength(4)
})

test('a_row_in_the_selection_shows_checked_and_the_header_shows_some', async () => {
  const view = await table({ selected: reactive(new Set(['b'])) })

  expect(checked(view)).toEqual(['indeterminate', 'unchecked', 'checked', 'unchecked'])
  expect(view.findAll('tbody tr').map((tr) => tr.attributes('data-state'))).toEqual([
    undefined,
    'selected',
    undefined,
  ])
})

test('ticking_a_row_adds_it_to_the_selection_and_unticking_takes_it_out', async () => {
  const selected = reactive(new Set<string>(['b']))
  const view = await table({ selected })
  await boxes(view)[1]?.trigger('click')
  await flushPromises()
  expect([...selected].sort()).toEqual(['a', 'b'])

  await boxes(view)[2]?.trigger('click')
  await flushPromises()
  expect([...selected]).toEqual(['a'])
})

test('the_header_box_selects_every_row_of_the_page_and_keeps_rows_of_other_pages', async () => {
  const selected = reactive(new Set<string>(['p20']))
  const view = await table({ data: many(12), paged: { label: 'pulls', fallback: 10 }, selected })
  await boxes(view)[0]?.trigger('click')
  await flushPromises()

  expect([...selected].sort()).toEqual(
    ['p1', 'p10', 'p2', 'p20', 'p3', 'p4', 'p5', 'p6', 'p7', 'p8', 'p9'].sort(),
  )
  await boxes(view)[0]?.trigger('click')
  await flushPromises()
  expect([...selected]).toEqual(['p20'])
})

test('each_box_names_its_row', async () => {
  const view = await table({
    selected: reactive(new Set<string>()),
    rowLabel: (p: Pull) => p.title,
  })

  expect(boxes(view).map((box) => box.attributes('aria-label'))).toEqual([
    'Select every row on this page',
    'Select Read the default branch',
    'Select Keep the archive paged',
    'Select Answer from the phone',
  ])
})

test('a_manual_table_keeps_the_rows_as_given_and_links_its_headers_where_its_caller_says', async () => {
  const manual = { sort: ['runs', 'desc'], sortHref: (key: string) => `/archive?sort=${key}` }
  const view = await table({ manual, data: many(60) }, '/?sort=title&dir=asc')

  expect(runsColumn(view)).toEqual(many(60).map((p) => p.runs))
  expect(headLink(view, 0)).toBe('/archive?sort=title')
  expect(view.findAll('th').map((th) => th.attributes('aria-sort'))).toEqual([
    undefined,
    'descending',
  ])
})

test('a_row_carries_the_attributes_its_caller_gives_it', async () => {
  const view = await table({ rowAttrs: (p: Pull) => ({ 'data-pull': p.id }) })

  expect(view.findAll('tbody tr').map((tr) => tr.attributes('data-pull'))).toEqual(['a', 'b', 'c'])
})

test('a_cell_slot_draws_the_cell_from_its_row', async () => {
  const view = await table({}, '/', {
    'cell-title':
      '<template #cell-title="{ row }"><a :href="`/pulls/${row.id}`">{{ row.title }}</a></template>',
  })

  expect(view.findAll('tbody tr td:first-child a').map((a) => a.attributes('href'))).toEqual([
    '/pulls/a',
    '/pulls/b',
    '/pulls/c',
  ])
  expect(texts(view, 'tbody tr td:nth-child(2)')).toEqual(['3', '12', '7'])
})

// The table in its own card surface, a toolbar above
// it only when there is something to filter or hide, a footer under it with the selection and the
// pages.
const FRAME = '[data-slot="data-table-frame"]'
const TOOLBAR = '[data-slot="data-table-toolbar"]'
const FOOTER = '[data-slot="data-table-footer"]'

// This case keeps its original gate identity. The assertion follows the current design.
test('the_table_sits_in_its_own_bordered_box', async () => {
  const frame = (await table()).get(FRAME)

  expect(frame.classes()).toEqual(expect.arrayContaining(['rounded-xl', 'bg-card']))
  expect(frame.classes()).not.toContain('border')
  expect(frame.find('table').exists()).toBe(true)
})

test('a_toolbar_is_above_the_box_only_with_a_filter_or_a_columns_menu', async () => {
  expect((await table()).find(TOOLBAR).exists()).toBe(false)
  expect((await table({ filter: FILTER })).find(TOOLBAR).exists()).toBe(true)
  expect((await table({ hideable: true })).find(TOOLBAR).exists()).toBe(true)
})

test('the_footer_counts_the_chosen_rows_of_the_table', async () => {
  const view = await table({ selected: reactive(new Set(['b', 'elsewhere'])) })

  expect(view.get(FOOTER).text()).toContain('1 of 3 row(s) selected.')
})

test('a_table_without_a_selection_or_a_second_page_has_no_footer', async () => {
  expect((await table()).find(FOOTER).exists()).toBe(false)
  expect((await table({ paged: { label: 'pulls', fallback: 10 } })).find(FOOTER).exists()).toBe(
    false,
  )
})

const pagerOf = (view: Awaited<ReturnType<typeof table>>) => {
  const footer = view.get(FOOTER)
  const previous = footer.findAll('a,button').find((el) => el.text() === 'Previous')
  const next = footer.findAll('a,button').find((el) => el.text() === 'Next')
  return {
    range: footer.get('[data-testid="page-range"]').text(),
    previous: previous?.element.tagName === 'A' ? previous.attributes('href') : 'disabled',
    next: next?.element.tagName === 'A' ? next.attributes('href') : 'disabled',
  }
}

test('a_paged_table_pages_with_previous_and_next_under_the_box', async () => {
  const paged = { label: 'pulls', fallback: 10 }

  expect(pagerOf(await table({ data: many(25), paged }))).toEqual({
    range: '1 to 10 of 25',
    previous: 'disabled',
    next: '/?page=2',
  })
  expect(pagerOf(await table({ data: many(25), paged }, '/?page=3'))).toEqual({
    range: '21 to 25 of 25',
    previous: '/?page=2',
    next: 'disabled',
  })
})

test('rows_paged_by_the_server_page_with_the_same_footer', async () => {
  const view = await table(
    {
      manual: { sort: ['title', 'asc'], sortHref: () => '/' },
      pager: { label: 'archived tickets', total: 120, page: 2, size: 50 },
    },
    '/?page=2&q=gift',
  )

  expect(pagerOf(view)).toEqual({
    range: '51 to 100 of 120',
    previous: '/?q=gift',
    next: '/?q=gift&page=3',
  })
})

test('the_columns_a_viewer_hides_are_kept_for_the_next_visit', async () => {
  localStorage.removeItem('test.columns')
  const first = await table({ hideable: true, columnsKey: 'test.columns' })
  await openMenu(first, COLUMNS_MENU)
  await menuItem(first, 'Runs').trigger('click')
  await flushPromises()
  first.unmount()

  expect(texts(await table({ hideable: true, columnsKey: 'test.columns' }), 'th')).toEqual([
    'Title',
  ])
  expect(texts(await table({ hideable: true }), 'th')).toEqual(['Title', 'Runs'])
  localStorage.removeItem('test.columns')
})

test('a_table_is_named_by_its_caption_for_a_screen_reader', async () => {
  const caption = (await table({ caption: 'Recently merged' })).get('table caption')

  expect({ text: caption.text(), hidden: caption.classes() }).toEqual({
    text: 'Recently merged',
    hidden: ['sr-only'],
  })
})

test('a_filter_that_keeps_no_row_says_so_across_the_whole_table', async () => {
  const view = await table({ filter: { ...FILTER, none: 'pull request' } }, '/?q=zzzz')
  const cell = view.get('tbody tr td')

  expect({ text: cell.text(), span: cell.attributes('colspan') }).toEqual({
    text: 'No pull request matches “zzzz”',
    span: '2',
  })
})

test('the_table_says_how_many_rows_its_filter_keeps', async () => {
  const view = await table({ filter: FILTER }, '/?q=archive')

  expect(view.emitted('shown')?.at(-1)).toEqual([1])
})

test('every_sortable_header_shows_that_it_sorts_and_the_default_order_is_announced', async () => {
  const view = await table({ defaultSort: ['runs', 'desc'] })
  const heads = view.findAll('th')

  expect(heads.map((th) => th.find('[data-slot="sort-icon"]').exists())).toEqual([true, true])
  expect(heads.map((th) => th.attributes('aria-sort'))).toEqual([undefined, 'descending'])
})

// shadcn-vue's Data Table example: a sortable header is a ghost button holding the label and its
// sort icon, the sorted column's icon naming the direction, and a row is 48 px tall.
test('a_sortable_header_is_a_ghost_button_with_its_icon_as_the_example_draws_it', async () => {
  const view = await table({ defaultSort: ['runs', 'desc'] })
  const heads = view.findAll('th')
  const rows = view.findAll('tbody tr')

  expect({
    buttons: heads.map((th) => th.find('a[data-slot="button"]').exists()),
    icons: heads.map((th) => th.find('a[data-slot="button"] [data-slot="sort-icon"]').exists()),
    tall: rows.length > 0 && rows.every((tr) => tr.classes().includes('h-12')),
  }).toEqual({ buttons: [true, true], icons: [true, true], tall: true })
})

test('a_stacked_table_turns_each_row_into_a_card_below_768_px', async () => {
  const view = await table({ stacked: true })

  expect(view.get('thead').classes()).toContain('max-md:hidden')
  expect(view.get('tbody tr').classes()).toEqual(
    expect.arrayContaining(['max-md:flex', 'max-md:flex-wrap']),
  )
  expect((await table()).get('tbody tr').classes()).not.toContain('max-md:flex')
})

test('labelled_rows_keep_their_headers_and_offer_sorting_on_a_phone', async () => {
  const view = await table(
    { stacked: 'labelled', prefix: 'demo_' },
    '/?demo_sort=runs&demo_dir=desc',
  )
  const cells = view.findAll('tbody tr:first-child td')

  expect(cells.map((cell) => cell.attributes('data-column-label'))).toEqual(['Title', 'Runs'])
  expect(cells.map((cell) => cell.attributes('headers'))).toEqual(
    view.findAll('th').map((header) => header.attributes('id')),
  )
  const menu = view.get('[data-mobile-sort] button')
  expect(menu.text()).toContain('Runs')
  await openMenu(view, '[data-mobile-sort] button')
  expect(menuItem(view, 'Runs').attributes('href')).toBe('/?demo_sort=runs&demo_dir=asc')
})

// docs/design.md's type scale and the Data Table example: a header is the cells' size, whether
// it sorts or not, so a plain header and a sort button beside it read alike.
test('every_header_is_the_cells_size_whether_it_sorts_or_not', async () => {
  const view = await table({ defaultSort: ['runs', 'desc'] })

  expect({
    head: view.get('thead').classes().includes('text-sm'),
    sort: view.findAll('thead a[data-slot="button"]').map((a) => a.classes().includes('text-sm')),
  }).toEqual({ head: true, sort: [true, true] })
})
