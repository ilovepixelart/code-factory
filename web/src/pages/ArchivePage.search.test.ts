// @vitest-environment happy-dom
// CF-847: characterization tests, written against the hand-written debounce before it moved to
// VueUse and passing before and after: the Archive search waits 200 ms after the last keystroke
// before it reaches the address, keeps a chosen sort, and is dropped when the page closes.

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, expect, test, vi } from 'vitest'
import type { Archive } from '../lib/memory'
import { answer, memoryRouter, provideBoard } from '../test/board'
import ArchivePage from './ArchivePage.vue'

const EMPTY: Archive = { rows: [], archived_count: 0, sort: 'archived', dir: 'desc' }

let page: VueWrapper | null = null

async function archivePage(address: string) {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(answer(EMPTY))),
  )
  const router = memoryRouter([
    { path: '/archive', component: ArchivePage },
    { path: '/:rest(.*)*', component: { template: '<div />' } },
  ])
  await router.push(address)
  const global = { plugins: [router], provide: provideBoard(), stubs: { teleport: true } }
  page = mount(ArchivePage, { attachTo: document.body, global })
  await flushPromises()
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  return { page, router }
}

afterEach(() => {
  page?.unmount()
  page = null
  vi.useRealTimers()
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

// CF-847-R3
test('the_archive_search_waits_200_ms_after_the_last_keystroke', async () => {
  const { page, router } = await archivePage('/archive')
  // The test's Teleport stub mounts the field again on each render, so the box is found again.
  const box = () => page.get('#archive-search')

  await box().setValue('CF')
  await vi.advanceTimersByTimeAsync(150)
  await box().setValue('CF-1')
  await vi.advanceTimersByTimeAsync(199)
  expect(router.currentRoute.value.fullPath).toBe('/archive')

  await vi.advanceTimersByTimeAsync(1)
  expect(router.currentRoute.value.fullPath).toBe('/archive?q=CF-1')

  await box().setValue('')
  await vi.advanceTimersByTimeAsync(200)
  expect(router.currentRoute.value.fullPath).toBe('/archive')
})

// CF-847-R3
test('the_archive_search_keeps_a_chosen_sort', async () => {
  const { page, router } = await archivePage('/archive?sort=id&dir=asc')

  await page.get('#archive-search').setValue('CF-1')
  await vi.advanceTimersByTimeAsync(200)

  expect(router.currentRoute.value.query).toEqual({ sort: 'id', dir: 'asc', q: 'CF-1' })
})

// CF-847-R4
test('the_archive_search_is_dropped_when_the_page_closes', async () => {
  const { page: open, router } = await archivePage('/archive')

  await open.get('#archive-search').setValue('CF-1')
  await vi.advanceTimersByTimeAsync(100)
  // Unmounting the router's only app resets its current route, so the replace itself is watched.
  const replace = vi.spyOn(router, 'replace')
  open.unmount()
  page = null
  await vi.advanceTimersByTimeAsync(500)

  expect(replace).not.toHaveBeenCalled()
})

test('the_archive_box_follows_the_address_without_searching', async () => {
  const { page, router } = await archivePage('/archive?q=foo')
  const replace = vi.spyOn(router, 'replace')

  await router.push('/archive')
  await flushPromises()
  await vi.advanceTimersByTimeAsync(500)

  expect((page.get('#archive-search').element as HTMLInputElement).value).toBe('')
  expect(replace).not.toHaveBeenCalled()
})

test('the_archive_box_following_the_address_keeps_the_rest_of_it', async () => {
  const { page, router } = await archivePage('/archive?q=foo&page=2&size=20')
  // A page the server serves as asked is not clamped by the page's own replace.
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(answer({ ...EMPTY, page: 2, size: 20 }))),
  )
  const replace = vi.spyOn(router, 'replace')

  await router.push('/archive?q=bar&page=2&size=20')
  await flushPromises()
  await vi.advanceTimersByTimeAsync(500)

  expect((page.get('#archive-search').element as HTMLInputElement).value).toBe('bar')
  expect(replace).not.toHaveBeenCalled()
  expect(router.currentRoute.value.query).toEqual({ q: 'bar', page: '2', size: '20' })
})

// The owner: with nothing archived the kinds have nothing to narrow, so they do not show.
test('with_nothing_archived_the_kinds_are_absent', async () => {
  const { page: view } = await archivePage('/archive')

  expect(view.find('nav[aria-label="Kind of archived ticket"]').exists()).toBe(false)
})

test('the_search_box_names_what_it_searches', async () => {
  const { page } = await archivePage('/archive')

  expect(page.get('#archive-search').attributes('placeholder')).toBe('Search by ID or title')
})
