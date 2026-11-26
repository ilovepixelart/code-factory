// The Factory pages' helpers: the range an address names as the dates the read sends, a share, the
// size words and the chart's points. Expected values are worked by hand from the specification
// (the definitions of section 3 and the worked fixture F1).

import { describe, expect, test } from 'vitest'
import { dashboard } from '../test/factory'
import { RANGES, bounds, chartPoints, prs, rangeOf, share, sizeLabel, windowWords } from './factory'

describe('the range', () => {
  test('a_range_runs_from_midnight_n_days_before_tomorrow_to_tomorrows_midnight_in_utc', () => {
    // 2026-11-10 23:30 UTC: today is inside, so the end is Nov 11; 7 days back is Nov 4.
    const now = new Date('2026-11-10T23:30:00Z')

    expect(bounds('7d', now)).toEqual({ from: '2026-11-04', to: '2026-11-11' })
    expect(bounds('30d', now)).toEqual({ from: '2026-10-12', to: '2026-11-11' })
    expect(bounds('90d', now)).toEqual({ from: '2026-08-13', to: '2026-11-11' })
  })

  test('the_range_follows_utc_not_the_zone_of_the_browser', () => {
    // 2026-11-10 00:30 UTC is still Nov 9 evening in New York; the dates are UTC's.
    expect(bounds('7d', new Date('2026-11-10T00:30:00Z')).to).toBe('2026-11-11')
    // The last second of Dec 31 UTC: tomorrow crosses the year.
    expect(bounds('7d', new Date('2026-12-31T23:59:59Z'))).toEqual({
      from: '2026-12-25',
      to: '2027-01-01',
    })
  })

  test('the_address_names_24h_7d_30d_or_90d_and_anything_else_reads_as_7d', () => {
    expect(RANGES.map(([key]) => key)).toEqual(['24h', '7d', '30d', '90d'])
    expect(rangeOf('24h')).toBe('24h')
    expect(rangeOf('90d')).toBe('90d')
    expect(rangeOf('1y')).toBe('7d')
    expect(rangeOf(undefined)).toBe('7d')
    expect(rangeOf(['7d', '90d'])).toBe('7d')
  })
})

describe('a share', () => {
  test('a_share_is_a_whole_percent_of_the_total', () => {
    // The fixture's runs by stage: 6 of 13 is 46.15, 1 of 13 is 7.69, 13 of 13 is 100.
    expect(share(6, 13)).toBe('46%')
    expect(share(1, 13)).toBe('8%')
    expect(share(13, 13)).toBe('100%')
  })

  test('a_share_of_nothing_is_a_dash_and_a_share_of_none_is_zero', () => {
    expect(share(0, 13)).toBe('0%')
    expect(share(0, 0)).toBe('-')
  })
})

describe('pull request counts', () => {
  test('a_count_of_pull_requests_is_singular_only_for_one', () => {
    expect(prs(0)).toBe('0 PRs')
    expect(prs(1)).toBe('1 PR')
    expect(prs(2)).toBe('2 PRs')
    expect(prs(1, 'merged')).toBe('1 merged PR')
    expect(prs(4, 'merged')).toBe('4 merged PRs')
  })
})

describe('the size words', () => {
  test('a_size_says_its_thresholds', () => {
    expect(sizeLabel('S')).toBe('S, under 100 lines')
    expect(sizeLabel('M')).toBe('M, 100 to 499 lines')
    expect(sizeLabel('L')).toBe('L, 500 to 999 lines')
    expect(sizeLabel('XL')).toBe('XL, 1000 lines and up')
  })

  test('a_size_not_recorded_reads_unknown', () => {
    expect(sizeLabel('unknown')).toBe('unknown')
    expect(sizeLabel(null)).toBe('unknown')
  })
})

describe('the window of a scorer', () => {
  test('a_window_is_named_in_whole_days', () => {
    expect(windowWords({ from: 1793664000, to: 1794268800 })).toBe('last 7 days')
    expect(windowWords({ from: 1793664000, to: 1793750400 })).toBe('last day')
  })
})

describe('the chart points', () => {
  test('a_week_of_buckets_is_labelled_by_day_and_month_in_utc', () => {
    const points = chartPoints(dashboard().series)

    expect(points.map((p) => p.label)).toEqual([
      '1 Nov',
      '2 Nov',
      '3 Nov',
      '4 Nov',
      '5 Nov',
      '6 Nov',
      '7 Nov',
    ])
    expect(points.map((p) => p.tick)).toEqual(points.map((p) => p.label))
    expect(points.map((p) => [p.opened, p.merged])).toEqual([
      [0, 0],
      [1, 1],
      [1, 1],
      [0, 0],
      [1, 1],
      [2, 0],
      [2, 1],
    ])
  })

  test('more_than_a_week_of_buckets_is_ticked_by_the_day_of_the_month', () => {
    const start = 1793491200
    const series = {
      bucket: 'day' as const,
      points: Array.from({ length: 9 }, (_, n) => ({
        start: start + n * 86_400,
        opened: 0,
        merged: 0,
      })),
    }

    expect(chartPoints(series).map((p) => p.tick)).toEqual([
      '1',
      '2',
      '3',
      '4',
      '5',
      '6',
      '7',
      '8',
      '9',
    ])
    expect(chartPoints(series)[8]?.label).toBe('9 Nov')
  })

  test('a_weekly_bucket_is_named_for_the_week_it_starts', () => {
    // Mondays Nov 2, 9 and 16 2026.
    const series = {
      bucket: 'week' as const,
      points: [1793577600, 1794182400, 1794787200].map((start) => ({
        start,
        opened: 1,
        merged: 0,
      })),
    }
    const points = chartPoints(series)

    expect(points.map((p) => p.label)).toEqual(['week of 2 Nov', 'week of 9 Nov', 'week of 16 Nov'])
    expect(points.map((p) => p.tick)).toEqual(['2 Nov', '9 Nov', '16 Nov'])
  })

  test('many_weekly_buckets_are_ticked_by_the_day_of_the_month', () => {
    const start = 1793577600
    const series = {
      bucket: 'week' as const,
      points: Array.from({ length: 9 }, (_, n) => ({
        start: start + n * 604_800,
        opened: 0,
        merged: 0,
      })),
    }

    expect(chartPoints(series)[1]?.tick).toBe('9')
  })
})
