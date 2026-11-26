// A unit test never reaches the network: its relative address would resolve against the test
// environment's own origin (localhost:3000) and its answer arrives whenever the machine allows,
// so a refusal can land in a later test. The baseline `fetch` records the call and refuses it, so
// a test that restores its globals gets the guard back; a test that sends requests installs its
// own with `stubFetch`. The test that made a call fails.

import { VueQueryPlugin, type QueryClient } from '@tanstack/vue-query'
import { config } from '@vue/test-utils'
import { afterEach, beforeEach, expect } from 'vitest'
import { createQueryClient } from '@/lib/queries'

const unstubbed: string[] = []

// Every mounted component gets the app's query client, a fresh one per test so no read's answer
// is cached into the next test.
let client: QueryClient | null = null
beforeEach(() => {
  client = createQueryClient()
  config.global.plugins = [[VueQueryPlugin, { queryClient: client }]]
})
afterEach(() => {
  client?.clear()
})

/** The query client every component mounted in this test reads through. */
export function testQueryClient(): QueryClient {
  if (!client) throw new Error('the query client exists only inside a test')
  return client
}

function refuse(input: unknown): Promise<Response> {
  const address = String(input instanceof Request ? input.url : input)
  unstubbed.push(address)
  return Promise.reject(new TypeError(`a unit test fetched ${address} without stubbing fetch`))
}

globalThis.fetch = refuse

beforeEach(() => {
  unstubbed.length = 0
})

afterEach(() => {
  expect([...unstubbed], 'requests sent without stubbing fetch').toEqual([])
})
