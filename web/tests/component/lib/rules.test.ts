// CF-325: the board's update and notification rules (docs/ui.md), with values worked from the
// rules by hand.

import { afterEach, describe, expect, test } from 'vitest'
import { shouldNotify } from '@/lib/attention'
import { standing } from '@/lib/folding'
import { readsNow } from '@/lib/live'
import { currentSort, daysSince, sortUrl } from '@/lib/memory'

afterEach(() => {
  localStorage.clear()
})

describe('desktop notifications', () => {
  test('a_notification_fires_only_when_the_count_grows_while_hidden', () => {
    expect(shouldNotify(null, 3, true, true)).toBe(false)
    expect(shouldNotify(2, 3, true, true)).toBe(true)
    expect(shouldNotify(3, 3, true, true)).toBe(false)
    expect(shouldNotify(4, 3, true, true)).toBe(false)
    expect(shouldNotify(2, 3, false, true)).toBe(false)
    expect(shouldNotify(2, 3, true, false)).toBe(false)
  })
})

describe('the live board', () => {
  test('a_held_board_reads_only_when_forced', () => {
    expect(readsNow(false, false)).toBe(true)
    expect(readsNow(true, false)).toBe(false)
    expect(readsNow(true, true)).toBe(true)
  })
})

describe('folded columns', () => {
  test('a_column_choice_drops_when_its_count_crosses_zero', () => {
    localStorage.setItem('codeFactoryColumns', JSON.stringify({ brd: true, frd: false, uat: true }))
    standing({ brd: 2, frd: 0, uat: 1 })

    const kept = standing({ brd: 0, frd: 3, uat: 4 })

    expect(kept).toEqual({ uat: true })
    expect(standing({ brd: 1, frd: 2, uat: 5 })).toEqual({ uat: true })
  })

  test('a_column_choice_stays_while_its_count_keeps_its_side_of_zero', () => {
    standing({ brd: 2, frd: 0 })
    localStorage.setItem('codeFactoryColumns', JSON.stringify({ brd: true, frd: false }))

    expect(standing({ brd: 5, frd: 0 })).toEqual({ brd: true, frd: false })
  })
})

describe('the archive and memory', () => {
  test('the_archive_sorts_by_a_known_column_else_newest_first', () => {
    expect(currentSort('title', 'asc')).toEqual(['title', 'asc'])
    expect(currentSort('nonsense', 'asc')).toEqual(['archived', 'desc'])
    expect(currentSort('', '')).toEqual(['archived', 'desc'])
  })

  test('a_sort_link_starts_descending_and_flips_the_current_column', () => {
    expect(sortUrl('', ['archived', 'desc'], 'title')).toBe('/archive?sort=title&dir=desc')
    expect(sortUrl('', ['title', 'desc'], 'title')).toBe('/archive?sort=title&dir=asc')
    expect(sortUrl('', ['title', 'asc'], 'title')).toBe('/archive?sort=title&dir=desc')
    expect(sortUrl('fix bug', ['archived', 'desc'], 'id')).toBe(
      '/archive?q=fix+bug&sort=id&dir=desc',
    )
    // CF-1191-R4: a sort keeps the page size and leaves the page out.
    expect(sortUrl('', ['archived', 'desc'], 'id', '10')).toBe('/archive?sort=id&dir=desc&size=10')
  })

  test('days_since_counts_whole_utc_days', () => {
    const noon = Date.parse('2026-10-06T12:00:00Z')
    expect(daysSince('2026-10-06', noon)).toBe(0)
    expect(daysSince('2026-10-05', noon)).toBe(1)
    expect(daysSince('2026-09-06', noon)).toBe(30)
    expect(daysSince('2026-10-07', noon)).toBe(-1)
  })
})
