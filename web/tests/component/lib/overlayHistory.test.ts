// CF-1272: an open overlay holds one history entry; Back closes the topmost overlay, and an overlay
// closed any other way gives its entry up, so Back never needs pressing twice.

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { enter, leave, settled, type Held } from '@/lib/overlayHistory'

const state = () => (history.state as Record<string, unknown> | null)?.codeFactoryOverlay ?? null
// Back, resolved once the page has heard it.
function back(): Promise<unknown> {
  const heard = new Promise((resolve) => {
    addEventListener('popstate', resolve, { once: true })
  })
  history.back()
  return heard
}

function overlay() {
  const close = vi.fn()
  return { close, entry: enter({ close }) }
}

let open: Held[] = []
// Entries below the one under test, so Back has a page to go to.
beforeEach(() => {
  history.pushState(null, '')
  history.pushState(null, '')
})
afterEach(async () => {
  for (const entry of open) leave(entry)
  open = []
  await settled()
})

test('opening_an_overlay_marks_one_history_entry', () => {
  const before = history.length
  const { entry } = overlay()
  open.push(entry)

  expect([history.length - before, state() !== null]).toEqual([1, true])
})

test('back_closes_the_overlay_and_leaves_the_page_where_it_was', async () => {
  const { close, entry } = overlay()
  open.push(entry)

  await back()

  expect([close.mock.calls.length, state()]).toEqual([1, null])
})

test('an_overlay_closed_another_way_pops_its_entry', async () => {
  const { close, entry } = overlay()

  leave(entry)
  await settled()

  expect([state(), close.mock.calls.length]).toEqual([null, 0])
})

test('back_after_an_overlay_closed_by_escape_is_not_taken_by_a_stale_entry', async () => {
  const { close, entry } = overlay()
  leave(entry)
  await settled()
  const hold = vi.fn()
  addEventListener('popstate', hold)

  await back()
  removeEventListener('popstate', hold)

  expect(close).not.toHaveBeenCalled()
  expect(hold).toHaveBeenCalledTimes(1)
})

test('back_closes_only_the_topmost_of_two_overlays', async () => {
  const lower = overlay()
  const upper = overlay()
  open.push(lower.entry, upper.entry)

  await back()

  expect([lower.close.mock.calls.length, upper.close.mock.calls.length]).toEqual([0, 1])
})

test('an_overlay_opened_while_another_is_popping_takes_its_entry_after_it', async () => {
  // A browser traverses history after the call returns; happy-dom does so within it.
  const traverse = history.back.bind(history)
  vi.spyOn(history, 'back').mockImplementation(() => {
    setTimeout(traverse)
  })
  const first = overlay()
  const firstMark = state()
  leave(first.entry)
  const second = overlay()
  open.push(second.entry)
  const early = state()

  await settled()
  vi.restoreAllMocks()

  expect([early, state() !== firstMark, state() !== null]).toEqual([firstMark, true, true])
  await back()
  expect(second.close).toHaveBeenCalledTimes(1)
})

test('an_overlay_closed_before_its_entry_was_pushed_never_pushes_one', async () => {
  const first = overlay()
  leave(first.entry)
  const second = overlay()
  leave(second.entry)

  await settled()

  expect(state()).toBeNull()
})

test('an_overlay_left_after_the_page_navigated_pops_nothing', async () => {
  const { entry } = overlay()
  history.pushState({ router: 'next' }, '')
  const length = history.length

  leave(entry)
  await settled()

  expect([history.length, (history.state as { router: string }).router]).toEqual([length, 'next'])
})
