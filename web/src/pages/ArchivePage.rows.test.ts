// @vitest-environment happy-dom
// CF-1207: an archive row says how the ticket left the board and when, opens the ticket, and
// shows Restore and Delete without a hover; the kinds are links that keep the rest of the address.

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, expect, test, vi } from 'vitest'
import type { Archive, ArchivedRow } from '../lib/memory'
import { sortUrl } from '../lib/memory'
import { answer, memoryRouter, provideBoard } from '../test/board'
import ArchivePage from './ArchivePage.vue'

const ROW = {
  repository: 'sample',
  type: 'feature',
  archived_at: 1_583_323_200, // 2020-03-04T12:00:00Z
  release: '',
}
const HAND: ArchivedRow = { ...ROW, id: 'CF-4', title: 'By hand', stage: 'build', archived: true }
const RELEASED: ArchivedRow = {
  ...ROW,
  id: 'CF-5',
  title: 'Shipped',
  stage: 'released',
  archived: false,
  release: '0.4.0',
}
const UNDATED: ArchivedRow = { ...HAND, id: 'CF-6', title: 'Undated', archived_at: 0 }

let page: VueWrapper | null = null

async function archivePage(address: string, rows: ArchivedRow[], archived = rows.length) {
  const body: Archive = { rows, archived_count: archived, sort: 'archived', dir: 'desc' }
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(answer({ ...body, total: rows.length, page: 1, size: 50 }))),
  )
  const router = memoryRouter([
    { path: '/archive', component: ArchivePage },
    { path: '/:rest(.*)*', component: { template: '<div />' } },
  ])
  await router.push(address)
  const global = { plugins: [router], provide: provideBoard(), stubs: { teleport: true } }
  page = mount(ArchivePage, { attachTo: document.body, global })
  await flushPromises()
  return page
}

afterEach(() => {
  page?.unmount()
  page = null
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

const rowOf = (p: VueWrapper, id: string) => p.get(`[data-archived-row="${id}"]`)

test('a_released_row_names_its_version_and_has_no_restore', async () => {
  const p = await archivePage('/archive', [RELEASED])

  const row = rowOf(p, 'CF-5')
  expect(row.text()).toContain('Released 0.4.0')
  expect(row.find('[aria-label="Restore CF-5"]').exists()).toBe(false)
  expect(row.find('[aria-label="Delete CF-5"]').exists()).toBe(true)
})

// A released row draws its stage glyph, the finished circle in the muted tone.
test('a_row_draws_its_stage_glyph', async () => {
  const p = await archivePage('/archive', [RELEASED])

  const glyph = rowOf(p, 'CF-5').get('svg[data-shape]')
  expect([glyph.attributes('data-shape'), glyph.classes()]).toEqual([
    'done',
    expect.arrayContaining(['text-muted-foreground']),
  ])
})

test('a_row_archived_by_hand_says_so_and_names_the_stage_it_left', async () => {
  const p = await archivePage('/archive', [HAND])

  expect(rowOf(p, 'CF-4').text()).toContain('Archived by hand')
  expect(rowOf(p, 'CF-4').text()).toContain('from Build')
})

test('every_row_shows_its_date_and_an_unknown_one_says_so', async () => {
  const p = await archivePage('/archive', [HAND, RELEASED, UNDATED])

  expect(rowOf(p, 'CF-4').text()).toContain('4 Mar 2020')
  expect(rowOf(p, 'CF-5').text()).toContain('4 Mar 2020')
  expect(rowOf(p, 'CF-6').text()).toContain('No date')
})

test('restore_is_a_visible_secondary_button_and_delete_is_visible_too', async () => {
  const p = await archivePage('/archive', [HAND])

  const restore = rowOf(p, 'CF-4').get('[aria-label="Restore CF-4"]')
  const remove = rowOf(p, 'CF-4').get('[aria-label="Delete CF-4"]')
  for (const button of [restore, remove]) {
    expect(button.classes()).not.toContain('opacity-0')
    expect(button.classes()).not.toContain('group-hover:opacity-100')
  }
  expect(restore.attributes('data-variant')).toBe('outline')
  expect(restore.text()).toBe('Restore')
})

test('the_id_column_is_headed_id_in_capitals', async () => {
  const p = await archivePage('/archive', [HAND])

  expect(p.findAll('thead th').map((th) => th.text())[0]).toBe('ID')
})

test('the_id_and_the_title_both_open_the_ticket', async () => {
  const p = await archivePage('/archive', [HAND])

  const links = rowOf(p, 'CF-4')
    .findAll('a')
    .map((a) => a.attributes('href'))
  expect(links).toEqual(['/tickets/sample/CF-4', '/tickets/sample/CF-4'])
})

test('the_kinds_are_links_that_keep_the_search_and_leave_the_page_out', async () => {
  const p = await archivePage('/archive?q=CF&show=hand&page=2&size=10', [HAND])

  const nav = p.get('nav[aria-label="Kind of archived ticket"]')
  const links = Object.fromEntries(nav.findAll('a').map((a) => [a.text(), a.attributes('href')]))
  expect(links).toEqual({
    All: '/archive?q=CF&size=10',
    Released: '/archive?q=CF&show=released&size=10',
    'By hand': '/archive?q=CF&show=hand&size=10',
  })
  expect(nav.get('[aria-current="page"]').text()).toBe('By hand')
})

test('a_sort_link_keeps_the_kind_shown', () => {
  expect(sortUrl('', ['archived', 'desc'], 'id', '', 'released')).toBe(
    '/archive?sort=id&dir=desc&show=released',
  )
})

test('the_page_asks_the_board_for_the_kind_in_its_address', async () => {
  await archivePage('/archive?show=released', [RELEASED])

  const [asked] = (vi.mocked(fetch).mock.calls[0] ?? []) as [string]
  expect(asked).toContain('show=released')
})

test('with_archived_tickets_the_kinds_show', async () => {
  const p = await archivePage('/archive', [HAND])

  expect(p.find('nav[aria-label="Kind of archived ticket"]').exists()).toBe(true)
})

/** The empty state's title, the section's description, and whether the kinds come before it. */
function emptyState(p: VueWrapper): [string, string, boolean] {
  const nav = p.get('nav[aria-label="Kind of archived ticket"]').element
  const title = p.get('[data-slot="empty-title"]')
  const description = p.find('[data-slot="section-description"]')
  return [
    title.text(),
    description.exists() ? description.text() : '',
    Boolean(nav.compareDocumentPosition(title.element) & Node.DOCUMENT_POSITION_FOLLOWING),
  ]
}

test('a_kind_with_no_ticket_says_which_kind_under_the_kinds', async () => {
  const p = await archivePage('/archive?show=hand', [], 4)

  expect(emptyState(p)).toEqual(['No ticket archived by hand', 'of 4 archived', true])
})

test('released_with_no_ticket_says_no_released_ticket', async () => {
  const p = await archivePage('/archive?show=released', [], 4)

  expect(emptyState(p)).toEqual(['No released ticket', 'of 4 archived', true])
})

test('a_search_with_no_match_keeps_the_kinds_above_the_message', async () => {
  const p = await archivePage('/archive?q=zebra', [], 4)

  expect(emptyState(p)).toEqual(['No archived ticket matches “zebra”', 'of 4 archived', true])
})
