// @vitest-environment happy-dom
// A page's polled read stops while the tab is hidden and reads again as it shows: a tab left open
// costs no requests. A read that must act while hidden (the Inbox count, which notifies) says so.

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { inQuery } from '../test/query'
import { usePolledRead } from './queries'

const TICK = 3000

let reads = 0

function seen(state: DocumentVisibilityState): void {
  Object.defineProperty(document, 'visibilityState', { value: state, configurable: true })
  // A browser's visibilitychange bubbles from the document to the window.
  document.dispatchEvent(new Event('visibilitychange', { bubbles: true }))
}

beforeEach(() => {
  vi.useFakeTimers()
  reads = 0
  seen('visible')
})

afterEach(() => {
  seen('visible')
  vi.useRealTimers()
})

const read = (): Promise<number> => Promise.resolve((reads += 1))

test('a_polled_read_stops_while_the_tab_is_hidden_and_reads_again_as_it_shows', async () => {
  const page = inQuery(() => usePolledRead(['page'], read, TICK))
  await vi.advanceTimersByTimeAsync(TICK)
  const shown = reads

  seen('hidden')
  await vi.advanceTimersByTimeAsync(TICK * 3)
  const hidden = reads - shown

  seen('visible')
  await vi.advanceTimersByTimeAsync(0)
  const back = reads - shown - hidden
  page.stop()

  expect({ shown: shown > 0, hidden, back }).toEqual({ shown: true, hidden: 0, back: 1 })
})

test('a_read_that_acts_while_hidden_keeps_polling', async () => {
  const page = inQuery(() => usePolledRead(['count'], read, TICK, { background: true }))
  await vi.advanceTimersByTimeAsync(0)
  const shown = reads

  seen('hidden')
  await vi.advanceTimersByTimeAsync(TICK * 3)
  page.stop()

  expect(reads - shown).toBe(3)
})
