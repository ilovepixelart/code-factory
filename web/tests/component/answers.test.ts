// CF-312: of overlapping reads, only the latest answer is applied, and a read that failed is not
// taken for a ticket that does not exist.

import { flushPromises, mount } from '@vue/test-utils'
import type { Component } from 'vue'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { useBoard } from '@/lib/live'
import { loadTicket } from '@/lib/ticket'
import MemoryPage from '@/pages/MemoryPage.vue'
import SessionPage from '@/pages/SessionPage.vue'
import { memoryRouter, provideBoard } from '../support/board'
import { inQuery } from '../support/query'

function json(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  })
}

/** A server whose answers are released by hand, in any order, per address. */
function server() {
  const waiting = new Map<string, ((r: Response) => void)[]>()
  const fetcher = vi.fn(
    (url: string) =>
      new Promise<Response>((resolve) => {
        waiting.set(url, [...(waiting.get(url) ?? []), resolve])
      }),
  )
  vi.stubGlobal('fetch', fetcher)
  const release = async (url: string, response: Response, newest = false) => {
    const queue = waiting.get(url) ?? []
    const next = newest ? queue.pop() : queue.shift()
    if (!next) throw new Error(`nothing asked for ${url}; asked: ${[...waiting.keys()].join(', ')}`)
    next(response)
    await flushPromises()
  }
  return { release }
}

const pages: { unmount: () => void }[] = []

async function mounted(component: Component, path: string, address: string) {
  document.body.innerHTML =
    '<div id="header-title"></div><div id="header-controls"></div><div id="app"></div>'
  const router = memoryRouter([{ path, component }])
  await router.push(address)
  const page = mount(component, {
    attachTo: '#app',
    global: {
      plugins: [router],
      provide: provideBoard(),
      stubs: { MemoryEntry: true, MemoryForm: true },
    },
  })
  pages.push(page)
  await flushPromises()
  return { page, router }
}

const memory = (snippet: string) => ({
  repositories: ['sample'],
  unreviewed: [],
  rules: [],
  decisions: [],
  lessons: [],
  retired: [],
  proposals: [],
  filing: null,
  left_out: [],
  pairs: [],
  review_queue: [],
  loaded_chars: 0,
  ceiling: 6000,
  results: [{ repository: 'sample', path: 'notes.md', snippet, open: '' }],
  matched: 1,
})

const session = (id: string) => ({
  session_id: id,
  cwd: `/work/${id}`,
  repository: '',
  branch: '',
  state: 'idle',
  last_event_at: 1_790_000_000,
  stale: false,
  current_action: null,
  subagents: [],
  last_prompt: '',
  turn_tool_calls: 0,
})

afterEach(() => {
  pages.splice(0).forEach((page) => {
    page.unmount()
  })
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

describe('only the latest answer is applied', () => {
  test('a_memory_search_shows_the_latest_query', async () => {
    const { release } = server()
    const { page, router } = await mounted(MemoryPage, '/memory', '/memory?q=ab')
    await router.push('/memory?q=abc')
    await flushPromises()

    await release('/api/memory?q=abc&page=1&size=50', json(memory('found for abc')))
    await release('/api/memory?q=ab&page=1&size=50', json(memory('found for ab')))

    expect(page.text()).toContain('found for abc')
    expect(page.text()).not.toMatch(/found for ab(?!c)/)
  })

  test('a_session_page_shows_the_session_it_is_on', async () => {
    const { release } = server()
    const { router } = await mounted(SessionPage, '/sessions/:id', '/sessions/session-alpha')
    await router.push('/sessions/session-beta')
    await flushPromises()

    await release(
      '/api/sessions/session-beta/timeline?last=500',
      json({ session: session('session-beta'), entries: [] }),
    )
    await release('/api/sessions/usage?session=session-beta', json({}))
    await release(
      '/api/sessions/session-alpha/timeline?last=500',
      json({ session: session('session-alpha'), entries: [] }),
    )
    await release('/api/sessions/usage?session=session-alpha', json({}))

    expect(document.body.textContent).toContain('session-beta')
    expect(document.body.textContent).not.toContain('session-alpha')
  })

  test('the_board_keeps_the_answer_read_after_a_change', async () => {
    const { release } = server()
    const shell = inQuery(() => useBoard())
    const live = shell.value
    const after = live.refresh({ force: true })
    // The read after the change is sent once the one under way is cancelled.
    await flushPromises()

    await release('/api/board', json({ today: 'after' }, 200, { ETag: '"2"' }), true)
    await after
    await release('/api/board', json({ today: 'before' }, 200, { ETag: '"1"' }))

    expect(live.board.value?.today).toBe('after')
    shell.stop()
  })
})

describe('a ticket that failed to load', () => {
  test('a_failed_read_is_not_a_missing_ticket', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(json({ detail: 'busy' }, 503))),
    )
    const missing = vi.fn(() => Promise.resolve(json({ detail: 'no ticket CF-9' }, 404)))

    await expect(loadTicket('sample', 'CF-1')).rejects.toThrow()
    vi.stubGlobal('fetch', missing)
    expect(await loadTicket('sample', 'CF-9')).toBeNull()
  })
})
