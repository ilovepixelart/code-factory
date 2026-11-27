import { expect, test } from 'vitest'
import { newestFirst, trailingDigits, type Card } from '@/lib/board'
import { sameServer } from '@/lib/connections'
import { cost, money, spendLevel, thousands, withoutTrailingSlashes } from '@/lib/format'
import { fromFolder } from '@/lib/session_view'

test('thousands_groups_a_digit_run_from_the_right', () => {
  const cases: [number | string, string][] = [
    [0, '0'],
    [999, '999'],
    [1000, '1,000'],
    [12345, '12,345'],
    [123456, '123,456'],
    [18240, '18,240'],
    [1234567, '1,234,567'],
    ['1234567890', '1,234,567,890'],
    ['1234.5678', '1,234.5,678'],
  ]
  for (const [value, expected] of cases) expect(thousands(value)).toBe(expected)
})

test('thousands_leaves_text_without_digits_alone', () => {
  expect(thousands('')).toBe('')
  expect(thousands('n/a')).toBe('n/a')
  expect(thousands('-1234')).toBe('-1,234')
})

test('money_rounds_an_exact_half_to_the_even_cent', () => {
  expect(money(0.125)).toBe('$0.12')
  expect(money(0.375)).toBe('$0.38')
  expect(money(2.675)).toBe('$2.67')
})

test('money_rounds_a_value_just_above_a_half_up', () => {
  expect(money(0.12500000000000003)).toBe('$0.13')
  expect(money(0.126)).toBe('$0.13')
  expect(money(0.124)).toBe('$0.12')
})

test('money_separates_thousands_and_signs_a_negative', () => {
  expect(money(1234.5)).toBe('$1,234.50')
  expect(money(-1234.5)).toBe('-$1,234.50')
})

test('cost_leads_with_a_tilde_only_when_estimated', () => {
  expect(cost(1234.5)).toBe('$1,234.50')
  expect(cost(1234.5, false)).toBe('$1,234.50')
  expect(cost(1234.5, true)).toBe('~$1,234.50')
})

test('spend_level_is_over_at_the_budget_watch_from_four_fifths_else_normal', () => {
  expect(spendLevel(1, null)).toBe('normal')
  expect(spendLevel(10, 10)).toBe('over')
  expect(spendLevel(8, 10)).toBe('watch')
  expect(spendLevel(7.99, 10)).toBe('normal')
})

test('trailing_slashes_are_removed_and_inner_ones_kept', () => {
  expect(withoutTrailingSlashes('/a/b///')).toBe('/a/b')
  expect(withoutTrailingSlashes('/a//b/')).toBe('/a//b')
  expect(withoutTrailingSlashes('/a/b')).toBe('/a/b')
  expect(withoutTrailingSlashes('///')).toBe('')
  expect(withoutTrailingSlashes('')).toBe('')
})

test('trailing_slashes_of_a_long_run_cost_one_pass', () => {
  expect(withoutTrailingSlashes(`${'/'.repeat(200_000)}x${'/'.repeat(200_000)}`)).toBe(
    `${'/'.repeat(200_000)}x`,
  )
})

test('a_server_path_ignores_its_trailing_slashes', () => {
  expect(sameServer('http://a:1/x/', 'http://a:1/x')).toBe(true)
  expect(sameServer('http://a:1/x//', 'http://a:1/x')).toBe(true)
  expect(sameServer('http://a:1/x/y', 'http://a:1/x')).toBe(false)
})

test('a_session_folder_is_stripped_from_paths_whatever_slashes_end_it', () => {
  expect(fromFolder('open /w/app/src/a.ts', '/w/app//')).toBe('open src/a.ts')
  expect(fromFolder('open /w/app/src/a.ts', '/w/app')).toBe('open src/a.ts')
  expect(fromFolder('open /w/app/src/a.ts', '/')).toBe('open /w/app/src/a.ts')
  expect(fromFolder('open /w/app/src/a.ts', '')).toBe('open /w/app/src/a.ts')
})

test('trailing_digits_are_the_run_that_ends_the_text', () => {
  expect(trailingDigits('CF-1077')).toBe('1077')
  expect(trailingDigits('CF-12-7')).toBe('7')
  expect(trailingDigits('CF-12x')).toBe('')
  expect(trailingDigits('')).toBe('')
  expect(trailingDigits('007')).toBe('007')
  expect(trailingDigits(`${'9'.repeat(100_000)}x`)).toBe('')
})

test('cards_are_newest_first_by_repository_then_the_number_in_the_id', () => {
  const card = (repository: string, id: string) => ({ repository, id }) as Card
  const sorted = newestFirst([
    card('b', 'CF-2'),
    card('a', 'CF-9'),
    card('a', 'CF-10'),
    card('a', 'x'),
  ])
  expect(sorted.map((c) => `${c.repository}/${c.id}`)).toEqual(['a/CF-10', 'a/CF-9', 'a/x', 'b/CF-2'])
})
