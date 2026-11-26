// @vitest-environment happy-dom
// A scorer's card: the pass rate as a whole percent, its answers and window, and on the Scorers
// page the yes, no and unclear counts behind the rate.

import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import { scorers } from '../../test/factory'
import ScorerCard from './ScorerCard.vue'

const card = () => {
  const [first] = scorers().cards
  if (!first) throw new Error('the fixture holds no scorer')
  return first
}

test('the_counts_behind_the_rate_show_only_on_request', () => {
  const plain = mount(ScorerCard, { props: { card: card() } })
  const detailed = mount(ScorerCard, { props: { card: card(), detail: true } })

  expect(plain.find('[data-counts]').exists()).toBe(false)
  expect(detailed.get('[data-counts]').text()).toBe('3 yes, 1 no, 1 unclear')
})

test('a_scorer_with_no_yes_or_no_answer_has_no_rate_and_a_dash_stands_for_it', () => {
  const none = { ...card(), yes: 0, no: 0, unclear: 2, asked: 2, pass_rate: null }
  const view = mount(ScorerCard, { props: { card: none } })

  expect(view.findAll('p').map((p) => p.text())).toContain('-')
  expect(view.text()).toContain('2 answers')
})

test('one_answer_is_not_plural', () => {
  const one = { ...card(), yes: 1, no: 0, unclear: 0, asked: 1, pass_rate: 1 }

  expect(mount(ScorerCard, { props: { card: one } }).text()).toContain('1 answer, last 7 days')
})
