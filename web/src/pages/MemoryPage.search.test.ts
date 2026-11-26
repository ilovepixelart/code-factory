// @vitest-environment happy-dom
// CF-847: characterization tests, written against the hand-written debounce before it moved to
// VueUse and passing before and after: the Memory search waits 200 ms after the last keystroke
// before it reaches the address, and a search pending when the page closes is dropped.

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, expect, test, vi } from 'vitest'
import type { Memory } from '../lib/memory'
import { answer, memoryRouter, provideBoard } from '../test/board'
import MemoryPage from './MemoryPage.vue'

const EMPTY: Memory = {
  repositories: ['sample'],
  unreviewed: [],
  rules: [],
  decisions: [],
  lessons: [],
  retired: [],
  proposals: [],
  loaded_chars: 0,
  ceiling: 4000,
  results: [],
  matched: 0,
  page: 1,
  size: 50,
  filing: null,
  left_out: [],
  pairs: [],
  review_queue: [],
}

let page: VueWrapper | null = null

async function memoryPage(address = '/memory') {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(answer(EMPTY))),
  )
  const router = memoryRouter([
    { path: '/memory', component: MemoryPage },
    { path: '/:rest(.*)*', component: { template: '<div />' } },
  ])
  await router.push(address)
  const global = { plugins: [router], provide: provideBoard(), stubs: { teleport: true } }
  page = mount(MemoryPage, { attachTo: document.body, global })
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

// CF-847-R1
test('the_memory_search_waits_200_ms_after_the_last_keystroke', async () => {
  const { page, router } = await memoryPage()
  // The test's Teleport stub mounts the field again on each render, so the box is found again.
  const box = () => page.get('#memory-search')

  await box().setValue('ru')
  await vi.advanceTimersByTimeAsync(150)
  await box().setValue('rule')
  await vi.advanceTimersByTimeAsync(199)
  expect(router.currentRoute.value.fullPath).toBe('/memory')

  await vi.advanceTimersByTimeAsync(1)
  expect(router.currentRoute.value.fullPath).toBe('/memory?q=rule')

  await box().setValue('')
  await vi.advanceTimersByTimeAsync(200)
  expect(router.currentRoute.value.fullPath).toBe('/memory')
})

// CF-847-R2
test('the_memory_search_is_dropped_when_the_page_closes', async () => {
  const { page: open, router } = await memoryPage()

  await open.get('#memory-search').setValue('rule')
  await vi.advanceTimersByTimeAsync(100)
  // Unmounting the router's only app resets its current route, so the replace itself is watched.
  const replace = vi.spyOn(router, 'replace')
  open.unmount()
  page = null
  await vi.advanceTimersByTimeAsync(500)

  expect(replace).not.toHaveBeenCalled()
})

test('the_memory_box_follows_the_address_without_searching', async () => {
  const { page, router } = await memoryPage('/memory?q=foo')
  const replace = vi.spyOn(router, 'replace')

  await router.push('/memory')
  await flushPromises()
  await vi.advanceTimersByTimeAsync(500)

  expect((page.get('#memory-search').element as HTMLInputElement).value).toBe('')
  expect(replace).not.toHaveBeenCalled()
})

test('the_memory_box_following_the_address_keeps_the_rest_of_it', async () => {
  const { page, router } = await memoryPage('/memory?q=foo&page=2')
  const replace = vi.spyOn(router, 'replace')

  await router.push('/memory?q=bar&page=2&why=none')
  await flushPromises()
  await vi.advanceTimersByTimeAsync(500)

  expect((page.get('#memory-search').element as HTMLInputElement).value).toBe('bar')
  expect(replace).not.toHaveBeenCalled()
  expect(router.currentRoute.value.query).toEqual({ q: 'bar', page: '2', why: 'none' })
})
