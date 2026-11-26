// @vitest-environment happy-dom
// CF-313: while the board does not answer, a poll waits for its next tick without raising an
// error, and an action shows that the board did not answer instead of throwing.

import { flushPromises, mount } from '@vue/test-utils'
import type { Component } from 'vue'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { ATTENTION, useAttention } from './lib/attention'
import { SECTIONS, type InboxItem } from './lib/metrics'
import InboxPage from './pages/InboxPage.vue'
import SessionPage from './pages/SessionPage.vue'
import SessionsPage from './pages/SessionsPage.vue'
import { memoryRouter, provideBoard } from './test/board'
import { present } from './test/present'
import { inQuery } from './test/query'

const unhandled: unknown[] = []
const record = (reason: unknown) => unhandled.push(reason)
const pages: { unmount: () => void }[] = []

beforeEach(() => {
  unhandled.length = 0
  process.on('unhandledRejection', record)
  document.body.innerHTML =
    '<div id="header-title"></div><div id="header-controls"></div><div id="app"></div>'
})

afterEach(() => {
  pages.splice(0).forEach((page) => {
    page.unmount()
  })
  process.off('unhandledRejection', record)
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

const down = () => Promise.reject(new TypeError('Failed to fetch'))

async function mounted(component: Component, address: string, errors: unknown[] = []) {
  const router = memoryRouter([
    { path: address.replace(/[^/]+$/, ':id'), component },
    { path: address, component },
  ])
  await router.push(address)
  const page = mount(component, {
    attachTo: '#app',
    global: {
      plugins: [router],
      config: { errorHandler: (error) => errors.push(error) },
      provide: {
        ...provideBoard(null, 'connecting'),
        [ATTENTION as symbol]: { refresh: () => Promise.resolve() },
      },
      stubs: { RouterLink: true },
    },
  })
  pages.push(page)
  await flushPromises()
  await new Promise((resolve) => setTimeout(resolve, 0))
  return page
}

describe('a board that does not answer', () => {
  test('a_poll_the_board_does_not_answer_raises_no_error', async () => {
    vi.stubGlobal('fetch', vi.fn(down))
    await mounted(InboxPage, '/inbox')
    await mounted(SessionsPage, '/')
    await mounted(SessionPage, '/sessions/session-alpha')
    const shell = inQuery(() => useAttention())

    await expect(shell.value.refresh()).resolves.toBeUndefined()
    await new Promise((resolve) => setTimeout(resolve, 0))
    shell.stop()

    expect(unhandled).toEqual([])
  })

  test('an_action_the_board_does_not_answer_shows_its_message', async () => {
    const request: InboxItem = {
      since: 1_790_000_000,
      kind: 'permission',
      reason: '',
      note: '',
      count: 1,
      images: [],
      ticket: { repository: 'sample', id: 'CF-1', title: 'First' },
      question: null,
      session: null,
      request: { id: 'r1', tool: 'Bash', summary: 'ls' },
    }
    const inbox = {
      ...Object.fromEntries(SECTIONS.map((s) => [s, [] as InboxItem[]])),
      permissions: [request],
      count: 1,
      latest: '',
      next_up: null,
    }
    let answering = true
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        answering ? Promise.resolve(new Response(JSON.stringify(inbox), { status: 200 })) : down(),
      ),
    )
    const errors: unknown[] = []
    const page = await mounted(InboxPage, '/inbox', errors)
    answering = false

    await present(
      page.findAll('button').find((b) => b.text() === 'Allow'),
      'Allow',
    ).trigger('click')
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(page.text()).toContain('The board did not answer; try again.')
    expect(errors).toEqual([])
    expect(unhandled).toEqual([])
  })
})
