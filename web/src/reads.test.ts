// @vitest-environment happy-dom
// CF-571: a page says it is reading until the board answers, says why when the board refuses or
// does not answer, offers to read again, and never shows an earlier query's answer under a new one.
// CF-1193: the Team page too.

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, test, vi } from 'vitest'
import type { Component } from 'vue'
import ArchivePage from './pages/ArchivePage.vue'
import FlowPage from './pages/FlowPage.vue'
import MemoryPage from './pages/MemoryPage.vue'
import SessionsPage from './pages/SessionsPage.vue'
import TeamPage from './pages/TeamPage.vue'
import { answer, memoryRouter, provideBoard } from './test/board'

const memory = (path: string) => ({
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
  ceiling: 4000,
  results: [{ repository: 'sample', path, snippet: 'a snippet', open: '' }],
  matched: 1,
})

const archive = (id: string) => ({
  rows: [
    {
      repository: 'sample',
      id,
      title: `Archived ${id}`,
      type: 'bug',
      stage: 'merged',
      archived: true,
      archived_at: 1_790_000_000,
      release: '',
    },
  ],
  archived_count: 1,
  sort: 'archived',
  dir: 'desc',
})

/** `page` mounted at `address` over a board whose `fetch` is `fetcher`. */
async function mounted(
  page: Component,
  path: string,
  address: string,
  fetcher: (url: string) => Promise<Response>,
) {
  vi.stubGlobal('fetch', vi.fn(fetcher))
  document.body.innerHTML = '<div id="header-controls"></div><div id="app"></div>'
  const router = memoryRouter([
    { path, component: page },
    { path: '/:rest(.*)*', component: { render: () => null } },
  ])
  await router.push(address)
  const global = { plugins: [router], provide: provideBoard(), stubs: { teleport: true } }
  const view = mount(page, { attachTo: '#app', global })
  await flushPromises()
  return { view, router }
}

const unanswered = () => Promise.reject(new TypeError('Failed to fetch'))

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

describe('the sessions page', () => {
  test('the_sessions_page_says_it_is_reading_before_the_first_answer', async () => {
    const { view } = await mounted(
      SessionsPage,
      '/',
      '/',
      () => new Promise<Response>(() => undefined),
    )

    expect(view.text()).toContain('Reading the sessions')
    expect(view.text()).not.toContain('No session is blocked')
  })

  test('the_sessions_page_says_when_the_board_does_not_answer', async () => {
    const { view } = await mounted(SessionsPage, '/', '/', unanswered)

    expect(view.text()).toContain('The board did not answer; try again.')
    expect(view.text()).not.toContain('No session is blocked')
  })
})

describe('a search the board refuses', () => {
  test('a_refused_memory_search_shows_why_and_not_the_last_results', async () => {
    const { view, router } = await mounted(MemoryPage, '/memory', '/memory?q=foo', (url) =>
      Promise.resolve(
        url.includes('q=bar')
          ? answer({ detail: 'the search is too long' }, 400)
          : answer(memory('docs/foo.md')),
      ),
    )
    await router.push('/memory?q=bar')
    await flushPromises()

    expect(view.text()).toContain('the search is too long')
    expect(view.text()).not.toContain('docs/foo.md')
  })

  test('a_refused_archive_search_shows_why_and_not_the_last_rows', async () => {
    const { view, router } = await mounted(ArchivePage, '/archive', '/archive?q=one', (url) =>
      Promise.resolve(
        url.includes('q=two')
          ? answer({ detail: 'the search is too long' }, 400)
          : answer(archive('CF-7')),
      ),
    )
    await router.push('/archive?q=two')
    await flushPromises()

    expect(view.text()).toContain('the search is too long')
    expect(view.text()).not.toContain('Archived CF-7')
  })
})

describe('a first read that fails', () => {
  test('a_memory_page_whose_read_failed_reads_again_on_request', async () => {
    let calls = 0
    const { view } = await mounted(MemoryPage, '/memory', '/memory?q=foo', () => {
      calls += 1
      return calls === 1 ? unanswered() : Promise.resolve(answer(memory('docs/foo.md')))
    })
    const offered = view.find('button[data-read-again]')
    expect([
      view.text().includes('The board did not answer; try again.'),
      offered.exists(),
    ]).toEqual([true, true])
    await offered.trigger('click')
    await flushPromises()

    expect(view.text()).toContain('docs/foo.md')
  })

  test('a_flow_page_whose_read_failed_says_so_and_reads_again_on_request', async () => {
    const fetcher = vi.fn<(url: string) => Promise<never>>(unanswered)
    const { view } = await mounted(FlowPage, '/analytics', '/analytics', fetcher)
    const offered = view.find('button[data-read-again]')
    expect([
      view.text().includes('The board did not answer; try again.'),
      offered.exists(),
    ]).toEqual([true, true])
    await offered.trigger('click')
    await flushPromises()

    expect(fetcher.mock.calls.filter(([url]) => url.startsWith('/api/flow'))).toHaveLength(2)
  })
})

describe('the team page', () => {
  // CF-1193-R3: no answer yet reads as reading, not as an empty page.
  test('the_team_page_says_it_is_reading_before_the_first_answer', async () => {
    const { view } = await mounted(TeamPage, '/', '/', () => new Promise<Response>(() => undefined))

    expect(view.text()).toContain('Reading the team')
  })

  // CF-1193-R3: a refused first read says why and offers to read again.
  test('the_team_page_says_why_its_first_read_failed', async () => {
    let calls = 0
    const { view } = await mounted(TeamPage, '/', '/', () => {
      calls += 1
      return Promise.resolve(answer({ detail: 'the board is busy' }, 503))
    })
    const offered = view.find('button[data-read-again]')
    expect([view.text().includes('the board is busy'), offered.exists()]).toEqual([true, true])
    await offered.trigger('click')
    await flushPromises()

    expect([calls, view.text().includes('Reading the team')]).toEqual([2, false])
  })
})
