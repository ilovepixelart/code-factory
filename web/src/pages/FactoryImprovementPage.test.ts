// @vitest-environment happy-dom
// The Self-improvement page lists the proposal pull requests, 20 to a page; not yet available is
// an empty state, not an error.

import { flushPromises } from '@vue/test-utils'
import { afterEach, expect, test, vi } from 'vitest'
import type { Improvements } from '../lib/factory'
import { improvements } from '../test/factory'
import { json, links, pageAt, words, readAgain } from '../test/factoryPage'
import FactoryImprovementPage from './FactoryImprovementPage.vue'

/** An improvement row's parts in order: its number, its title, its state and its age. */
const PARTS = '[data-slot="item-media"], [data-slot="item-title"], [data-slot="item-actions"] > *'

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

const show = (answer: Improvements = improvements(), address = '/analytics/self-improvement') =>
  pageAt(FactoryImprovementPage, address, () => json(answer))

const many = (n: number): Improvements => {
  const [first] = improvements().items
  if (!first) throw new Error('no fixture item')
  return {
    available: true,
    items: Array.from({ length: n }, (_, i) => ({
      ...first,
      url: `${first.url}-${String(i)}`,
      number: 100 + i,
    })),
  }
}

test('the_page_asks_for_20', async () => {
  const { sent } = await show()

  expect(sent.map((s) => s.url)).toEqual(['/api/factory/improvements?limit=20'])
})

test('an_item_shows_its_number_title_state_and_age', async () => {
  await show()

  // Clock Nov 10 15:00, opened Nov 6 21:20: 3 days 17h 40m, 3.7 days.
  expect(
    [...(document.querySelector('[data-slot="item"]')?.querySelectorAll(PARTS) ?? [])].map(words),
  ).toEqual(['#21', 'Self-improvement: 25 failures', 'Open', '3.7d ago'])
})

test('twenty_rows_show_on_a_page_and_the_rest_are_a_page_away', async () => {
  await show(many(25))

  expect(document.querySelectorAll('[data-slot="item"]')).toHaveLength(20)
  expect(document.body.textContent).toContain('1 to 20 of 25')
})

test('the_second_page_holds_the_rest', async () => {
  const { router } = await show(many(25))

  await router.push('/analytics/self-improvement?page=2')
  await flushPromises()

  expect(document.querySelectorAll('[data-slot="item"]')).toHaveLength(5)
})

test('not_yet_available_says_what_it_will_be_and_is_no_error', async () => {
  await show({ available: false, items: [] })

  expect(
    ['empty-title', 'empty-description'].map((slot) =>
      document.querySelector(`[data-slot="${slot}"]`)?.textContent.trim(),
    ),
  ).toStrictEqual([
    'Self-improvement is not available yet',
    'Self-improvement groups scorer failures into one proposal pull request.',
  ])
  expect(document.querySelector('[role="alert"]')).toBeNull()
})

test('available_with_none_says_there_are_none_yet', async () => {
  await show({ available: true, items: [] })

  expect(document.body.textContent).toContain('No self-improvement pull requests yet')
})

test('the_header_switch_marks_this_page_current_and_there_is_no_range_switch', async () => {
  await show()

  expect(links('Analytics pages').map((l) => l.current)).toEqual([null, null, null]) // its tab is hidden (HIDDEN_TABS)
  expect(links('Range')).toEqual([])
})

test('until_the_first_answer_the_page_says_it_is_reading', async () => {
  await pageAt(
    FactoryImprovementPage,
    '/analytics/self-improvement',
    () => new Promise<Response>(() => undefined),
  )

  expect(document.body.textContent).toContain('Reading the self-improvement pull requests')
})

test('a_refused_read_shows_the_sentence_and_reads_again', async () => {
  let refuse = true
  await pageAt(FactoryImprovementPage, '/analytics/self-improvement', () =>
    refuse
      ? json({ detail: 'limit must be a whole number from 1 to 50' }, 400)
      : json(improvements()),
  )
  expect(document.querySelector('[role="alert"]')?.textContent).toContain('limit must be')

  refuse = false
  readAgain()
  await flushPromises()

  expect(document.querySelectorAll('[data-slot="item"]')).toHaveLength(1)
})
