// @vitest-environment happy-dom
// Flow's chart of pull requests: opened and merged per bucket, read to a screen reader as each
// bucket with its two counts, its legend naming both series and its description the bucket size.

import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import type { ChartPoint } from '../../lib/factory'
import PullsChart from './PullsChart.vue'

const points: ChartPoint[] = [
  { start: 1_794_268_800, opened: 3, merged: 2, label: '9 Nov', tick: '9 Nov' },
  { start: 1_794_355_200, opened: 0, merged: 0, label: '10 Nov', tick: '10 Nov' },
]

const chart = (weekly: boolean) => mount(PullsChart, { props: { points, weekly } })

test('the_chart_reads_as_each_bucket_with_its_opened_and_merged_counts', () => {
  expect(chart(false).get('[role="img"]').attributes('aria-label')).toBe(
    '9 Nov: opened 3, merged 2; 10 Nov: opened 0, merged 0',
  )
})

test('the_description_names_the_bucket_size', () => {
  expect(chart(false).get('[data-slot="card-description"]').text()).toBe(
    'Pull requests the board opened per day, and those of them merged',
  )
  expect(chart(true).get('[data-slot="card-description"]').text()).toBe(
    'Pull requests the board opened per week, and those of them merged',
  )
})

test('the_heading_names_the_chart_for_the_page', () => {
  expect(chart(false).get('h2#shipped-heading').text()).toBe('Shipped')
})

// The owner: a range with no pull request draws no empty grid; the chart's Card says so instead.
test('a_range_with_no_pull_request_shows_an_empty_state_in_place_of_the_chart', () => {
  const quiet = mount(PullsChart, {
    props: { points: points.map((p) => ({ ...p, opened: 0, merged: 0 })), weekly: false },
  })
  const none = mount(PullsChart, { props: { points: [], weekly: false } })

  expect(
    [quiet, none].map((view) => [
      view.find('[role="img"]').exists(),
      view.find('[data-slot="card"] [data-slot="empty-title"]').text(),
    ]),
  ).toStrictEqual([
    [false, 'The board opened no pull request in this range'],
    [false, 'The board opened no pull request in this range'],
  ])
})

// Shipped above counts every merge git recorded; the chart counts only what the board opened, so
// its empty state must not claim that nothing merged.
test('the_empty_chart_does_not_contradict_the_shipped_count', () => {
  const none = mount(PullsChart, { props: { points: [], weekly: false } })

  expect(none.get('[data-slot="empty-description"]').text()).toBe(
    'Shipped counts every merge git recorded, opened by the board or not.',
  )
})

test('a_range_with_a_pull_request_draws_the_chart', () => {
  expect(chart(false).find('[data-slot="empty"]').exists()).toBe(false)
})
