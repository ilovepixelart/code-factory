// @vitest-environment happy-dom
// CF-847: characterization test, written against the hand-written title assignment before it
// moved to VueUse and passing before and after: the tab title carries the Inbox count.

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, test, vi } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import { pageTitle, useAttention } from './attention'

const POLL_MS = 5000

const page = ref('')
const Host = defineComponent({
  setup() {
    useAttention(page)
    return () => h('div')
  },
})

afterEach(() => {
  page.value = ''
  vi.useRealTimers()
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

// CF-847-R5
test('the_tab_title_carries_the_inbox_count', async () => {
  const counts = [
    { count: 3, latest: 'CF-1 asks' },
    { count: 0, latest: '' },
  ]
  vi.useFakeTimers()
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(new Response(JSON.stringify(counts.shift()), { status: 200 }))),
  )
  document.title = 'before'
  const view = mount(Host, { attachTo: document.body })
  await flushPromises()
  expect(document.title).toBe('(3) code-factory')

  await vi.advanceTimersByTimeAsync(POLL_MS)
  await flushPromises()
  expect(document.title).toBe('code-factory')
  view.unmount()
})

// CF-1162-R6: a page's claim on the title holds over the inbox count's polls, and released, the
// count comes back.
test('a_page_claims_the_tab_title_over_the_inbox_count', async () => {
  vi.useFakeTimers()
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve(new Response(JSON.stringify({ count: 3, latest: '' }), { status: 200 })),
    ),
  )
  const view = mount(Host, { attachTo: document.body })
  await flushPromises()

  pageTitle.value = '(2) Team'
  await flushPromises()
  expect(document.title).toBe('(2) Team · code-factory')
  await vi.advanceTimersByTimeAsync(POLL_MS)
  await flushPromises()
  expect(document.title).toBe('(2) Team · code-factory')

  pageTitle.value = ''
  await flushPromises()
  expect(document.title).toBe('(3) code-factory')
  view.unmount()
})

// WCAG 2.4.2: each tab names its page between the inbox count and the product's name.
test('the_tab_title_names_the_page_after_the_inbox_count', async () => {
  vi.useFakeTimers()
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve(new Response(JSON.stringify({ count: 6, latest: '' }), { status: 200 })),
    ),
  )
  page.value = 'Tickets'
  const view = mount(Host, { attachTo: document.body })
  await flushPromises()
  const tickets = document.title

  page.value = 'Memory'
  await flushPromises()

  expect([tickets, document.title]).toEqual([
    '(6) Tickets · code-factory',
    '(6) Memory · code-factory',
  ])
  view.unmount()
})
