// The one status mark (docs/design.md, Theme): a status word on a Badge, its tone from the status
// map and its word from the word map, in sentence case wherever it shows.

import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import { TONE_VARIANTS } from '@/lib/status_tone'
import StatusBadge from '@/components/StatusBadge.vue'

const badge = (props: Record<string, unknown>, slot?: string) =>
  mount(StatusBadge, { props, ...(slot === undefined ? {} : { slots: { default: slot } }) })

test.each([
  ['working', 'Working', TONE_VARIANTS.info],
  ['blocked', 'Waiting on you', TONE_VARIANTS.warning],
  ['owner', 'Waiting on you', TONE_VARIANTS.warning],
  ['waiting', 'Waiting', TONE_VARIANTS.warning],
  ['stale', 'Stale', TONE_VARIANTS.warning],
  ['merged', 'Merged', TONE_VARIANTS.success],
  ['open', 'Open', TONE_VARIANTS.info],
  ['checks failing', 'Checks failing', TONE_VARIANTS.error],
])('the_%s_state_reads_%s_on_a_%s_badge', (state, words, shown) => {
  const view = badge({ state })

  expect([view.text(), view.attributes('data-slot'), view.attributes('data-variant')]).toEqual([
    words,
    'badge',
    shown,
  ])
})

test.each(['ended', 'idle'])('the_%s_state_is_quiet', (state) => {
  expect(badge({ state }).attributes('data-variant')).toBe(TONE_VARIANTS.quiet)
})

test('a_quiet_badge_keeps_the_word_without_the_colour', () => {
  expect([
    badge({ state: 'working', quiet: true }).text(),
    badge({ state: 'working', quiet: true }).attributes('data-variant'),
    badge({ state: 'working' }).attributes('data-variant'),
  ]).toEqual(['Working', TONE_VARIANTS.quiet, TONE_VARIANTS.info])
})

test('an_unknown_state_reads_in_sentence_case_on_the_quiet_badge', () => {
  const view = badge({ state: 'odd thing' })

  expect([view.text(), view.attributes('data-variant')]).toEqual(['Odd thing', TONE_VARIANTS.quiet])
})

test('a_tone_with_its_own_words_draws_that_tone', () => {
  const view = badge({ tone: 'warning' }, 'No source')

  expect([view.text(), view.attributes('data-variant')]).toEqual([
    'No source',
    TONE_VARIANTS.warning,
  ])
})

test('the_words_given_win_over_the_state_word', () => {
  expect(badge({ state: 'open' }, 'Open #12').text()).toBe('Open #12')
})
