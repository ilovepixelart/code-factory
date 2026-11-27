// The Scorers page reads the scorers of the range its address names and draws each as a card with
// the counts behind its pass rate; not yet available is an empty state, not an error.

import { flushPromises } from '@vue/test-utils'
import { afterEach, expect, test, vi } from 'vitest'
import { scorers } from '../../support/factory'
import { json, links, pageAt, words, readAgain } from '../../support/factoryPage'
import FactoryScorersPage from '@/pages/FactoryScorersPage.vue'

/** A scorer's lines in order: its title, its descriptions, the lines of its body, its rate. */
const LINES = '[data-slot="item-title"], [data-slot="item-description"], p'

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

const show = (address = '/analytics/scorers', answer = scorers()) =>
  pageAt(FactoryScorersPage, address, () => json(answer))

test('the_page_reads_the_scorers_of_the_range_with_today_inside', async () => {
  const { sent } = await show('/analytics/scorers?range=7d')

  expect(sent.map((s) => s.url)).toEqual([
    '/api/factory/scorers?from=2026-11-03T15:00:00.000Z&to=2026-11-10T15:00:00.000Z',
  ])
})

test('the_range_and_the_pages_are_links_and_this_page_is_current', async () => {
  await show()

  expect(links('Range').map((l) => l.href)).toEqual([
    '/analytics/scorers?range=24h',
    '/analytics/scorers',
    '/analytics/scorers?range=30d',
    '/analytics/scorers?range=90d',
  ])
  expect(links('Analytics pages').map((l) => l.current)).toEqual([null, null, 'page'])
})

test('a_card_shows_the_question_the_counts_the_rate_and_the_window', async () => {
  await show()

  const card = document.querySelector('[data-scorer]')
  expect([...(card?.querySelectorAll(LINES) ?? [])].map((p) => words(p))).toEqual([
    'ran-tests',
    'Did the agent run the tests before finishing?',
    '5 answers, last 7 days',
    '3 yes, 1 no, 1 unclear',
    '75%',
  ])
})

test('scorers_not_yet_available_say_what_they_will_be_and_are_no_error', async () => {
  await show('/analytics/scorers', { available: false, cards: [] })

  expect(document.body.textContent).toContain(
    'Scorers are not available yetScorers judge completed runs against criteria you write.',
  )
  expect(document.querySelector('[role="alert"]')).toBeNull()
})

test('available_with_no_scorer_says_where_to_define_one', async () => {
  await show('/analytics/scorers', { available: true, cards: [] })

  expect(document.body.textContent).toContain(
    'No scorers definedAdd [[scorers]] to .code-factory/config.toml.',
  )
})

test('until_the_first_answer_the_page_says_it_is_reading_the_scorers', async () => {
  await pageAt(
    FactoryScorersPage,
    '/analytics/scorers',
    () => new Promise<Response>(() => undefined),
  )

  expect(document.body.textContent).toContain('Reading the scorers')
})

test('a_refused_read_shows_the_sentence_and_reads_again', async () => {
  let refuse = true
  await pageAt(FactoryScorersPage, '/analytics/scorers', () =>
    refuse ? json({ detail: 'from must be before to' }, 400) : json(scorers()),
  )
  expect(document.querySelector('[role="alert"]')?.textContent).toContain('from must be before to')

  refuse = false
  readAgain()
  await flushPromises()

  expect(document.querySelectorAll('[data-scorer]')).toHaveLength(1)
})

test('a_range_change_reads_again_keeping_the_cards_with_a_loading_line', async () => {
  let release: (r: Response) => void = () => undefined
  let hold = false
  const { router } = await pageAt(FactoryScorersPage, '/analytics/scorers', () =>
    hold ? new Promise<Response>((r) => (release = r)) : json(scorers()),
  )

  hold = true
  await router.push('/analytics/scorers?range=90d')
  await flushPromises()
  expect(document.querySelectorAll('[data-scorer]')).toHaveLength(1)
  expect(document.querySelector('[data-reading]')).not.toBeNull()

  release(json({ available: true, cards: [] }))
  await flushPromises()
  expect(document.querySelectorAll('[data-scorer]')).toHaveLength(0)
  expect(document.querySelector('[data-reading]')).toBeNull()
})
