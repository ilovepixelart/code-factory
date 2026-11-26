// CF-1162, CF-1209: a Team row draws its state, ticket, actor, line, pull request and age, then
// each other state of its ticket as a second line.

import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import { memoryRouter } from '../../../support/board'
import { NOW, teamRow } from '../../../support/team'
import TeamTable from '@/components/team/TeamTable.vue'

process.env.TZ = 'UTC'

const draw = (row = teamRow(), selected = false) =>
  mount(TeamTable, {
    props: { rows: [row], caption: 'Team work', now: NOW, selected: selected ? row.key : '' },
    global: { plugins: [memoryRouter()] },
    attachTo: document.body,
  })

test('a_row_draws_its_state_ticket_title_actor_line_and_age', () => {
  const view = draw()
  const text = view.text()
  expect(text).toContain('Working')
  expect(view.get('a.font-mono').text()).toBe('CF-1')
  expect(view.get('a.font-mono').attributes('href')).toBe('/tickets/sample/CF-1')
  expect(view.get('button').text()).toBe('Build the thing')
  expect(text).toContain('builder')
  expect(text).toContain('build run')
  expect(text).toContain('9m')
})

test('a_stale_row_draws_its_state_word', () => {
  expect(draw(teamRow({ state: 'stale', line: 'agent failed (exit 1)' })).text()).toContain('Stale')
})

test('a_row_waiting_on_the_owner_says_so', () => {
  expect(draw(teamRow({ state: 'owner' })).text()).toContain('Waiting on you')
})

test('a_done_row_says_when_it_merged', () => {
  const view = draw(
    teamRow({ state: 'merged', line: 'builder', since: NOW - 7200, until: NOW - 3600 }),
  )
  expect(view.text()).toContain('Merged')
  expect(view.text()).toContain('merged at 11:00, builder')
  expect(view.text()).toContain('1h')
})

test('a_row_draws_its_pull_request_number_link_and_words', () => {
  const view = draw(
    teamRow({
      pull: { number: 20, url: 'https://example.test/pull/20', gate: 'passed', merge: 'open' },
    }),
  )
  const link = view.get('a[href="https://example.test/pull/20"]')
  expect(link.text()).toBe('#20')
  expect(view.text()).toContain('checks passed')
})

test('a_row_without_a_pull_request_draws_none', () => {
  expect(draw().find('a[href^="https://"]').exists()).toBe(false)
})

test('a_row_draws_each_other_state_of_its_ticket_under_its_line', () => {
  const view = draw(
    teamRow({
      also: [
        {
          state: 'stale',
          actor: { kind: 'agent', name: 'builder' },
          line: 'agent failed (exit 1)',
          since: NOW - 4 * 86_400,
          until: null,
        },
      ],
    }),
  )
  expect(view.findAll('[data-also]').map((line) => line.text())).toEqual([
    'also stale 4d: builder, agent failed (exit 1)',
  ])
})

test('a_row_without_a_title_is_headed_by_its_ticket_and_without_a_ticket_by_its_actor', () => {
  const untitled = draw(teamRow({ ticket: { repository: 'sample', id: 'CF-2', title: '' } }))
  expect(untitled.get('button').attributes('aria-label')).toBe('Details for CF-2')
  const ticketless = draw(teamRow({ ticket: null, actor: { kind: 'gate', name: 'the gate' } }))
  expect(ticketless.get('button').text()).toBe('the gate')
})

test('a_selected_row_is_pressed_and_pressing_it_asks_to_select_it', async () => {
  const view = draw(teamRow(), true)
  expect(view.get('button').attributes('aria-pressed')).toBe('true')
  await view.get('button').trigger('click')
  expect(view.emitted('select')).toHaveLength(1)
  expect(draw().get('button').attributes('aria-pressed')).toBe('false')
})
