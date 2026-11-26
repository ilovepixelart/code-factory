import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, test } from 'vitest'
import { count, day, dur, labelColor, money, span, trim } from '@/lib/format'
import { turns, type Entry } from '@/lib/sessions'
import { expectGolden } from '../support/golden'

/** The formats this harness covers. */
const FORMATS = ['display'] as const

const folder = join(import.meta.dirname, '../../../tests/support/golden/formats', FORMATS[0])

interface Display {
  labels: Record<string, string>
  money: [number, string][]
  days: { raw: string; date: string | null; today: string; text: string }[]
  count: [number, string][]
  dur: [number | null, string][]
  span: [number, string][]
  trim: [string, number, string][]
  turns: (Omit<ReturnType<typeof turns>[number], 'entries'> & { entries: number[] })[][]
}

const cases = JSON.parse(readFileSync(join(folder, 'cases.json'), 'utf8')) as {
  turn_entries: Entry[][]
}

const golden = JSON.parse(readFileSync(join(folder, 'cases.golden.json'), 'utf8')) as Display

describe('the board writes values as the display goldens hold them', () => {
  // CF-490: one way for every age and span of time, worked by hand from the requirement.
  test('every_span_of_time_reads_one_way', () => {
    const seconds = [0, 29, 59.4, 59.5, 90, 3599, 3600, 5400, 86399, 86400, 129600, 885600, -5]

    expect(seconds.map((s) => span(s))).toStrictEqual([
      '0s',
      '29s',
      '59s',
      '1m',
      '2m',
      '60m',
      '1h',
      '1.5h',
      '24h',
      '1d',
      '1.5d',
      '10.2d',
      '0s',
    ])
  })

  test('display_formats_match_the_goldens', () => {
    expect(Object.keys(golden.labels).length).toBeGreaterThan(5)
    expect(golden.count.length).toBeGreaterThan(5)
    expect(golden.span.length).toBeGreaterThan(5)
    const produced: Display = {
      labels: Object.fromEntries(
        Object.keys(golden.labels).map((label) => [label, labelColor(label)]),
      ),
      money: golden.money.map(([value]) => [value, money(value)]),
      days: golden.days.map(({ raw, date, today }) => ({
        raw,
        date,
        today,
        text: day(date, raw, today),
      })),
      count: golden.count.map(([value]) => [value, count(value)]),
      dur: golden.dur.map(([seconds]) => [seconds, dur(seconds)]),
      span: golden.span.map(([seconds]) => [seconds, span(seconds)]),
      trim: golden.trim.map(([text, limit]) => [text, limit, trim(text, limit)]),
      turns: cases.turn_entries.map((entries) =>
        turns(entries).map((t) => ({ ...t, entries: t.entries.map((e) => e.seq) })),
      ),
    }

    expectGolden(join(folder, 'cases.golden.json'), { ...golden, ...produced })
  })
})
