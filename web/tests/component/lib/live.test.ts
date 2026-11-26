// CF-1235: the board is polled only while a page that shows it is open and the tab is seen;
// otherwise it is read as the app opens and after a change.

import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { inQuery } from '../../support/query'
import { useBoard, type Live } from '@/lib/live'

const TICK = 3000

let reads = 0
let refusing = false

function seen(state: DocumentVisibilityState): void {
  Object.defineProperty(document, 'visibilityState', { value: state, configurable: true })
  // A browser's visibilitychange bubbles from the document to the window.
  document.dispatchEvent(new Event('visibilitychange', { bubbles: true }))
}

beforeEach(() => {
  vi.useFakeTimers()
  reads = 0
  refusing = false
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      if (url === '/api/board') reads += 1
      const body = refusing ? { detail: 'not signed in' } : { today: '2026-11-11' }
      return Promise.resolve(
        new Response(JSON.stringify(body), {
          status: refusing ? 403 : 200,
          headers: { 'Content-Type': 'application/json', ETag: '"1"' },
        }),
      )
    }),
  )
})

afterEach(() => {
  seen('visible')
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

let opened: ReturnType<typeof inQuery<Live>> | null = null

function shell() {
  opened = inQuery(() => useBoard())
  return { live: opened.value, stop: opened.stop }
}

/** A page following `live` until the function returned is called, as a page is left. */
function page(live: Live): () => void {
  if (!opened) throw new Error('open the shell first')
  return opened.beside(() => {
    live.follow()
  })
}

describe('the live board', () => {
  test('a busy board keeps the last answer and recovers on the next poll', async () => {
    const { live, stop } = shell()
    await vi.advanceTimersByTimeAsync(0)
    const board = live.board.value
    expect(board).not.toBeNull()
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(null, { status: 503, headers: { 'Retry-After': '1' } }),
    )

    await live.refresh()

    expect(live.board.value).toBe(board)
    expect(live.state.value).toBe('reconnecting')
    await vi.advanceTimersByTimeAsync(TICK)
    expect(live.state.value).toBe('live')
    stop()
  })

  test('an older request that fails cannot mark the latest successful read as stale', async () => {
    const { live, stop } = shell()
    await vi.advanceTimersByTimeAsync(0)
    let fail: () => void = () => undefined
    vi.mocked(fetch).mockImplementationOnce(
      () =>
        new Promise((_resolve, reject) => {
          fail = () => {
            reject(new Error('offline'))
          }
        }),
    )

    const old = live.refresh()
    await live.refresh()
    fail()
    await old

    expect(live.state.value).toBe('live')
    stop()
  })

  test('without_a_page_that_shows_it_the_board_is_read_once', async () => {
    const { stop } = shell()

    await vi.advanceTimersByTimeAsync(5 * TICK)

    expect(reads).toBe(1)
    stop()
  })

  test('a_page_that_shows_the_board_polls_it_every_tick', async () => {
    const { live, stop } = shell()
    await vi.advanceTimersByTimeAsync(0)
    const leave = page(live)

    await vi.advanceTimersByTimeAsync(0)
    const arrived = reads
    await vi.advanceTimersByTimeAsync(2 * TICK)

    expect(arrived).toBe(2)
    expect(reads).toBe(4)
    leave()
    stop()
  })

  test('a_page_opened_with_the_app_adds_no_read_to_the_first', async () => {
    const { live, stop } = shell()
    const leave = page(live)

    await vi.advanceTimersByTimeAsync(0)
    const first = reads
    await vi.advanceTimersByTimeAsync(TICK)

    expect(first).toBe(1)
    expect(reads).toBe(2)
    leave()
    stop()
  })

  test('leaving_the_last_page_that_shows_the_board_stops_the_poll', async () => {
    const { live, stop } = shell()
    const first = page(live)
    const second = page(live)
    await vi.advanceTimersByTimeAsync(0)

    first()
    await vi.advanceTimersByTimeAsync(TICK)
    const stillShown = reads
    second()
    await vi.advanceTimersByTimeAsync(5 * TICK)

    expect(stillShown).toBe(2)
    expect(reads).toBe(2)
    stop()
  })

  test('a_hidden_tab_stops_the_poll_and_reads_as_it_is_seen_again', async () => {
    const { live, stop } = shell()
    const leave = page(live)
    await vi.advanceTimersByTimeAsync(0)

    seen('hidden')
    await vi.advanceTimersByTimeAsync(5 * TICK)
    const hidden = reads
    seen('visible')
    await vi.advanceTimersByTimeAsync(0)

    expect(hidden).toBe(1)
    expect(reads).toBe(2)
    leave()
    stop()
  })

  test('a_tab_seen_again_reads_nothing_on_a_page_that_does_not_show_the_board', async () => {
    const { stop } = shell()
    await vi.advanceTimersByTimeAsync(0)

    seen('hidden')
    seen('visible')
    await vi.advanceTimersByTimeAsync(5 * TICK)

    expect(reads).toBe(1)
    stop()
  })

  test('a_change_reads_the_board_on_a_page_that_does_not_show_it', async () => {
    const { live, stop } = shell()
    await vi.advanceTimersByTimeAsync(0)

    await live.refresh({ force: true })
    await vi.advanceTimersByTimeAsync(5 * TICK)

    expect(reads).toBe(2)
    stop()
  })

  test('a_read_sends_the_last_etag_and_a_304_keeps_the_board', async () => {
    const { live, stop } = shell()
    await vi.advanceTimersByTimeAsync(0)
    const board = live.board.value
    vi.mocked(fetch).mockResolvedValueOnce(new Response(null, { status: 304 }))

    await live.refresh()

    const [, sent] = vi.mocked(fetch).mock.calls[1] ?? []
    expect(new Headers(sent?.headers).get('If-None-Match')).toBe('"1"')
    expect(live.board.value).toBe(board)
    expect(live.state.value).toBe('live')
    stop()
  })

  test('a_held_board_drops_the_read_under_way_and_polls_nothing_until_released', async () => {
    const { live, stop } = shell()
    const leave = page(live)
    await vi.advanceTimersByTimeAsync(0)
    const board = live.board.value
    let answer: (response: Response) => void = () => undefined
    vi.mocked(fetch).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          reads += 1
          answer = resolve
        }),
    )
    await vi.advanceTimersByTimeAsync(TICK)

    live.hold(true)
    answer(new Response(JSON.stringify({ today: 'dropped' }), { status: 200 }))
    await vi.advanceTimersByTimeAsync(5 * TICK)
    const whileHeld = reads
    const shownWhileHeld = live.board.value
    live.hold(false)
    await live.refresh()

    expect(whileHeld).toBe(2)
    expect(shownWhileHeld).toBe(board)
    expect(reads).toBe(3)
    leave()
    stop()
  })

  test('a_forced_read_while_held_applies_and_runs_before_apply_first', async () => {
    const { live, stop } = shell()
    await vi.advanceTimersByTimeAsync(0)
    live.hold(true)
    const seen: (string | undefined)[] = []

    await live.refresh()
    await live.refresh({
      force: true,
      beforeApply: () => seen.push(live.board.value?.today),
    })

    expect(reads).toBe(2)
    expect(seen).toEqual(['2026-11-11'])
    stop()
  })

  test('a_board_that_has_not_answered_is_read_every_tick_until_it_answers', async () => {
    refusing = true
    const { live, stop } = shell()
    await vi.advanceTimersByTimeAsync(2 * TICK)
    const refused = reads
    const reason = live.refused.value

    refusing = false
    await vi.advanceTimersByTimeAsync(TICK)
    const answered = reads
    await vi.advanceTimersByTimeAsync(5 * TICK)

    expect(reason).toBe('not signed in')
    expect(refused).toBe(3)
    expect(answered).toBe(4)
    expect(reads).toBe(4)
    expect(live.state.value).toBe('live')
    stop()
  })
  test('a_read_that_fails_keeps_its_reason_until_a_read_answers', async () => {
    const { live, stop } = shell()
    await vi.advanceTimersByTimeAsync(0)
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'boom' }), {
        status: 500,
        headers: { 'Content-Type': 'application/problem+json' },
      }),
    )
    await live.refresh()
    const reason = live.failed.value
    vi.mocked(fetch).mockRejectedValueOnce(new TypeError('Failed to fetch'))
    await live.refresh()
    const unanswered = live.failed.value

    await live.refresh()

    expect(reason).toBe('boom')
    expect(unanswered).toBe('The board did not answer; try again.')
    expect(live.failed.value).toBe('')
    stop()
  })

  test('a_refused_read_is_not_a_failed_one', async () => {
    refusing = true
    const { live, stop } = shell()
    await vi.advanceTimersByTimeAsync(0)

    expect(live.refused.value).toBe('not signed in')
    expect(live.failed.value).toBe('')
    stop()
  })
})
