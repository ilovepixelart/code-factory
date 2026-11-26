// CF-1203: merges a day over the window. CF-1215: which merges did not hold, and their share of
// the window's merges.

import { afterEach, beforeEach, expect, test } from 'vitest'
import type { Merged } from '@/lib/metrics'
import { heldList, notHeld, perDay, share } from '@/lib/shipped'

let zone: string | undefined
beforeEach(() => {
  zone = process.env.TZ
  process.env.TZ = 'UTC'
})
afterEach(() => {
  process.env.TZ = zone
})

// 2026-11-10T12:00:00Z
const NOON = 1_794_312_000
const merge = (at: number): Merged => ({
  repository: 'sample',
  pull: 1,
  url: null,
  branch: 'ticket/cf-1',
  ticket: 'CF-1',
  title: '',
  at,
  lead: 0,
  from: 'filed',
  reverted: false,
  fixes: [],
  checks: 'passed',
  autonomy: 'unknown',
})

test('merges_a_day_over_the_window', () => {
  expect(perDay(14, NOON - 7 * 86_400, NOON)).toBe(2)
  expect(perDay(3, NOON - 3600, NOON)).toBe(72)
})

test('a_merge_did_not_hold_when_reverted_fixed_later_or_not_checked', () => {
  const held = merge(NOON)
  const reverted: Merged = { ...held, reverted: true }
  const fixed: Merged = { ...held, fixes: ['CF-9'] }
  const failed: Merged = { ...held, checks: 'failed' }
  const unrecorded: Merged = { ...held, checks: 'none' }
  const all = [held, reverted, fixed, failed, unrecorded]

  expect(all.filter((m) => notHeld(m, 'reverted'))).toEqual([reverted])
  expect(all.filter((m) => notHeld(m, 'fixed'))).toEqual([fixed])
  expect(all.filter((m) => notHeld(m, 'unchecked'))).toEqual([failed, unrecorded])
})

test('a_share_is_a_whole_percent_rounded_half_up', () => {
  expect(share(1, 3)).toBe(33)
  expect(share(2, 3)).toBe(67)
  expect(share(1, 8)).toBe(13)
  expect(share(4, 4)).toBe(100)
  expect(share(0, 5)).toBe(0)
  expect(share(0, 0)).toBe(0)
})

test('a_held_list_keeps_the_window_and_size_and_starts_at_the_first_page', () => {
  const query = { range: '30d', merged_page: '2', merged_size: '25', held: 'fixed' }

  expect(heldList(query, 'reverted')).toEqual({
    path: '/analytics',
    query: { range: '30d', merged_size: '25', held: 'reverted' },
  })
  expect(heldList(query, null)).toEqual({
    path: '/analytics',
    query: { range: '30d', merged_size: '25' },
  })
})
