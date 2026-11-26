// @vitest-environment happy-dom
// CF-1303: the Scorers table of the Agents page.

import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import type { Scorer } from '../lib/scorers'
import { memoryRouter } from '../test/board'
import ScorersSection from './ScorersSection.vue'

function scorer(extra: Partial<Scorer>): Scorer {
  return {
    repository: 'sample',
    name: 'ran-tests',
    question: 'Did the session run the tests?',
    stage: '',
    sample: 1,
    threshold: 10,
    week: { yes: 3, no: 1, unclear: 0, pass_rate: 0.75 },
    month: { yes: 9, no: 3, unclear: 2, pass_rate: 0.75 },
    ticket: '',
    ...extra,
  }
}

async function shown(scorers: Scorer[]) {
  const router = memoryRouter()
  await router.push('/agents')
  return mount(ScorersSection, { props: { scorers }, global: { plugins: [router] } })
}

test('a_scorer_row_shows_its_question_the_answers_asked_and_both_pass_rates', async () => {
  const view = await shown([scorer({})])
  const row = view.get('[data-scorer]')

  expect(view.get('caption').text()).toBe('Scorers')
  expect(row.get('td:nth-child(1)').text()).toBe('ran-tests')
  expect(row.get('td:nth-child(2)').text()).toBe('Did the session run the tests?')
  expect(row.get('[data-asked]').text()).toBe('14')
  expect(row.get('[data-week]').text()).toBe('75%')
  expect(row.get('[data-month]').text()).toBe('75%')
  expect(row.get('td:nth-child(6)').text()).toBe('none')
})

// Every table draws its figures alike: right-aligned under a right-aligned header.
test('the_three_figures_of_a_scorer_are_right_aligned_under_their_headers', async () => {
  const view = await shown([scorer({})])
  const right = (el: { classes: () => string[] }) => el.classes().includes('text-right')

  expect(
    ['[data-asked]', '[data-week]', '[data-month]'].map((cell) => right(view.get(cell))),
  ).toEqual([true, true, true])
  expect(view.findAll('th').slice(2, 5).map(right)).toEqual([true, true, true])
})

test('a_window_with_no_yes_or_no_answer_has_a_dash_not_a_rate', async () => {
  const empty = { yes: 0, no: 0, unclear: 2, pass_rate: null }
  const view = await shown([scorer({ week: empty })])

  expect(view.get('[data-week]').text()).toBe('-')
})

test('an_open_ticket_links_to_the_ticket', async () => {
  const view = await shown([scorer({ ticket: 'CF-9' })])
  const link = view.get('td:nth-child(6) a')

  expect(link.text()).toBe('CF-9')
  expect(link.attributes('href')).toBe('/tickets/sample/CF-9')
})

// The same scorer is often defined in several repositories: without the repository the rows read
// as duplicates.
test('scorers_from_several_repositories_name_their_repository', async () => {
  const view = await shown([scorer({ repository: 'web' }), scorer({ repository: 'infra' })])

  expect(view.findAll('[data-scorer] [data-repository]').map((cell) => cell.text())).toStrictEqual([
    'web',
    'infra',
  ])
  expect(view.findAll('th').map((th) => th.text())).toContain('Repository')
})

test('scorers_of_one_repository_leave_the_repository_out', async () => {
  const view = await shown([scorer({ name: 'a' }), scorer({ name: 'b' })])

  expect(view.find('[data-repository]').exists()).toBe(false)
})
