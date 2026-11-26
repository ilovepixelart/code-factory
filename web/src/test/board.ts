// What the component tests mount with: the golden API answers, a router in memory and the live
// board provided as the shell provides it.

import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { ref, shallowRef } from 'vue'
import { vi } from 'vitest'
import { createMemoryHistory, createRouter, type RouteRecordRaw } from 'vue-router'
import type { Board } from '../lib/board'
import { BOARD, type Live, type LiveState } from '../lib/live'

/** A golden API answer, `tests/golden/formats/api/<name>`. */
export function golden(name: string): unknown {
  return JSON.parse(
    readFileSync(join(import.meta.dirname, '../../../tests/golden/formats/api', name), 'utf8'),
  )
}

export const goldenBoard = (): Board => golden('board.golden.json') as Board

/** A router in memory; by default every address shows an empty page. */
export function memoryRouter(
  routes: RouteRecordRaw[] = [{ path: '/:rest(.*)*', component: { template: '<div />' } }],
) {
  return createRouter({ history: createMemoryHistory(), routes })
}

/** A JSON answer from the board, as `fetch` resolves it. */
export function answer(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** A request a page sent: its method, address and JSON body. */
export interface Sent {
  method: string
  url: string
  body: unknown
}

/** Answer every request with `reply`; the requests sent are kept, in order, in the list returned. */
export function stubFetch(
  reply: (url: string, init: RequestInit | undefined) => Response | Promise<Response>,
): Sent[] {
  const sent: Sent[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      const body: unknown = typeof init?.body === 'string' ? JSON.parse(init.body) : undefined
      sent.push({ method: init?.method ?? 'GET', url, body })
      return Promise.resolve(reply(url, init))
    }),
  )
  return sent
}

/** The live board with its refresh and hold recorded, and the `provide` entry holding it. */
export function spiedBoard(board: Board | null = null) {
  const live = {
    board: shallowRef<Board | null>(board),
    state: ref<LiveState>('live'),
    refused: ref(''),
    failed: ref(''),
    refresh: vi.fn<Live['refresh']>(() => Promise.resolve()),
    hold: vi.fn<Live['hold']>(),
    follow: vi.fn<Live['follow']>(),
  }
  return { live, provide: { [BOARD as symbol]: live } }
}

/** The `provide` entry holding the live board. */
export function provideBoard(board: Board | null = null, state: LiveState = 'live', failed = '') {
  return {
    [BOARD as symbol]: {
      board: shallowRef<Board | null>(board),
      state: ref(state),
      refused: ref(''),
      failed: ref(failed),
      refresh: () => Promise.resolve(),
      hold: () => undefined,
      follow: () => undefined,
    },
  }
}
