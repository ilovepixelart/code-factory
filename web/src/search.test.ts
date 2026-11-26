// @vitest-environment happy-dom
// CF-315: leaving a page cancels the search typed on it, so its query never reaches the address
// of the page opened next.

import { flushPromises, mount } from '@vue/test-utils'
import { type Component } from 'vue'
import { afterEach, describe, expect, test, vi } from 'vitest'
import ArchivePage from './pages/ArchivePage.vue'
import MemoryPage from './pages/MemoryPage.vue'
import { memoryRouter, provideBoard } from './test/board'
import { present } from './test/present'

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

/** Type into the page's search, leave for `/flow` before the search runs, then let it run. */
async function typeAndLeave(component: Component, path: string, input: string) {
  vi.useFakeTimers()
  vi.stubGlobal(
    'fetch',
    vi.fn(() => new Promise<Response>(() => undefined)),
  )
  document.body.innerHTML =
    '<div id="header-title"></div><div id="header-controls"></div><div id="app"></div>'
  const router = memoryRouter([
    { path, component },
    { path: '/flow', component: { template: '<p>flow</p>' } },
  ])
  await router.push(path)
  const page = mount(component, {
    attachTo: '#app',
    global: {
      plugins: [router],
      provide: provideBoard(),
      stubs: { RouterLink: true, MemoryEntry: true, MemoryForm: true },
    },
  })
  await flushPromises()
  const box = present(document.querySelector<HTMLInputElement>(input), input)
  box.value = 'typed then left'
  box.dispatchEvent(new Event('input'))
  await flushPromises()

  page.unmount()
  await router.push('/flow')
  await vi.advanceTimersByTimeAsync(1000)
  return router.currentRoute.value.fullPath
}

describe('a search typed just before leaving', () => {
  test('leaving_the_memory_page_cancels_its_search', async () => {
    expect(await typeAndLeave(MemoryPage, '/memory', '#memory-search')).toBe('/flow')
  })

  test('leaving_the_archive_cancels_its_search', async () => {
    expect(await typeAndLeave(ArchivePage, '/archive', 'input[type="search"]')).toBe('/flow')
  })
})
