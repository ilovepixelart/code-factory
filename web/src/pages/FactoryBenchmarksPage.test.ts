// @vitest-environment happy-dom
// The Benchmarks page is a placeholder: it reads nothing and says what benchmarks will be.

import { afterEach, expect, test, vi } from 'vitest'
import { json, links, pageAt } from '../test/factoryPage'
import FactoryBenchmarksPage from './FactoryBenchmarksPage.vue'

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

test('the_page_makes_no_request_and_says_benchmarks_arrive_with_the_evals_additions', async () => {
  const { sent } = await pageAt(FactoryBenchmarksPage, '/analytics/benchmarks', () => json({}))

  expect(sent).toEqual([])
  expect(
    ['empty-title', 'empty-description'].map((slot) =>
      document.querySelector(`[data-slot="${slot}"]`)?.textContent.trim(),
    ),
  ).toStrictEqual([
    'Benchmarks are not available yet',
    'Benchmarks compare models, runtimes and runners on the same fixed tasks.',
  ])
})

test('the_header_switch_marks_this_page_current', async () => {
  await pageAt(FactoryBenchmarksPage, '/analytics/benchmarks', () => json({}))

  expect(links('Analytics pages').map((l) => l.current)).toEqual([null, null, null]) // its tab is hidden (HIDDEN_TABS)
})

test('the_toolbar_keeps_its_row_and_says_the_page_reads_no_range', async () => {
  await pageAt(FactoryBenchmarksPage, '/analytics/benchmarks', () => json({}))

  const toolbar = document.querySelector('[data-analytics-toolbar]')
  expect(toolbar?.textContent.trim()).toBe('Not limited to a range')
  expect(document.querySelector('nav[aria-label="Range"]')).toBeNull()
})

// The header's h1 already reads Benchmarks: the card names what it will hold.
test('the_card_heading_does_not_repeat_the_page_title', async () => {
  await pageAt(FactoryBenchmarksPage, '/analytics/benchmarks', () => json({}))

  expect(document.getElementById('benchmarks-heading')?.textContent.trim()).toBe('Results')
})
