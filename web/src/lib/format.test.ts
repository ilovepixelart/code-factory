import { expect, test } from 'vitest'
import { dayClock, hourMinute } from './format'

process.env.TZ = 'UTC'

const at = (iso: string) => Date.parse(iso) / 1000

// 24-hour clock, two digits each, in the browser's zone.
test('hours_and_minutes_are_two_digits_on_a_24_hour_clock', () => {
  expect(hourMinute(at('2026-11-10T00:00:00Z'))).toBe('00:00')
  expect(hourMinute(at('2026-11-10T00:05:59Z'))).toBe('00:05')
  expect(hourMinute(at('2026-11-10T12:00:00Z'))).toBe('12:00')
  expect(hourMinute(at('2026-11-10T15:07:09Z'))).toBe('15:07')
  expect(hourMinute(at('2026-11-10T23:59:59Z'))).toBe('23:59')
})

test('hours_and_minutes_follow_the_zone_of_the_browser', () => {
  process.env.TZ = 'Asia/Kolkata'
  try {
    expect(hourMinute(at('2026-11-10T12:00:00Z'))).toBe('17:30')
  } finally {
    process.env.TZ = 'UTC'
  }
})

test('a_day_and_minute_end_in_the_hours_and_minutes', () => {
  const now = at('2026-11-10T12:00:00Z')
  expect(dayClock(at('2026-11-06T09:12:30Z'), now)).toBe('6 Nov 09:12')
})
