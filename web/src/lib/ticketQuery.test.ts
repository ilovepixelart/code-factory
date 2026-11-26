// @vitest-environment happy-dom
// The filter box's text and the address's `q` follow each other; only typing starts a new search.

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, test } from 'vitest'
import { defineComponent, h } from 'vue'
import { memoryRouter } from '../test/board'
import { useTicketQuery, type TicketQuery } from './ticketQuery'

async function filterAt(address: string) {
  const router = memoryRouter()
  await router.push(address)
  let filter!: TicketQuery
  const host = defineComponent({
    setup() {
      filter = useTicketQuery()
      return () => h('div')
    },
  })
  const page = mount(host, { global: { plugins: [router] } })
  await flushPromises()
  return { page, router, filter }
}

let open: { unmount: () => void } | null = null

afterEach(() => {
  open?.unmount()
  open = null
})

test('going_back_to_an_address_keeps_its_page', async () => {
  const { page, router, filter } = await filterAt('/tickets/list?q=a&page=3')
  open = page

  await router.push('/tickets/list?q=b')
  await flushPromises()
  router.back()
  await flushPromises()

  expect(router.currentRoute.value.query).toEqual({ q: 'a', page: '3' })
  expect(filter.needle.value).toBe('a')
})

test('typing_a_new_needle_starts_at_the_first_page', async () => {
  const { page, router, filter } = await filterAt('/tickets/list?q=a&page=3&size=20')
  open = page

  filter.needle.value = 'new'
  await flushPromises()

  expect(router.currentRoute.value.query).toEqual({ q: 'new', size: '20' })
})
