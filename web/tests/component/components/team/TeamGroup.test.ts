// CF-1162, CF-1209: a Team group draws its title and count, its rows or its empty line, and what
// its slot adds under them.

import { mount } from '@vue/test-utils'
import { computed } from 'vue'
import { expect, test } from 'vitest'
import type { Paged } from '@/lib/paging'
import type { TeamRow } from '@/lib/teamNow'
import { memoryRouter } from '../../../support/board'
import { NOW, teamRow } from '../../../support/team'
import TeamGroup from '@/components/team/TeamGroup.vue'
import { BotIcon, UserGroupIcon } from '@hugeicons/core-free-icons'
import { draws } from '../../../support/icons'

function paged(rows: TeamRow[], total = rows.length): Paged<TeamRow> {
  return {
    rows: computed(() => rows),
    total: computed(() => total),
    page: computed(() => 1),
    size: computed(() => 10),
  }
}

const draw = (rows: TeamRow[], total?: number, selected = '') =>
  mount(TeamGroup, {
    props: {
      id: 'team-working',
      title: 'Working',
      hint: 'longest first',
      empty: 'Nobody is working',
      next: 'Start an agent on a ticket and it works here.',
      icon: UserGroupIcon,
      paged: paged(rows, total),
      now: NOW,
      selected,
      prefix: 'working_',
    },
    slots: { default: '<p data-extra>Idle: builder</p>' },
    global: { plugins: [memoryRouter()] },
  })

test('a_group_draws_its_title_count_hint_and_one_row_each', () => {
  const view = draw([teamRow({ key: 'a' }), teamRow({ key: 'b', state: 'stale' })])
  expect(view.get('h2').text()).toContain('Working')
  expect(view.get('h2').text()).toContain('2')
  expect(view.text()).toContain('longest first')
  expect(view.get('table caption').text()).toBe('Working')
  expect(view.findAll('tbody tr').map((li) => li.attributes('data-row'))).toEqual(['a', 'b'])
})

test('a_group_without_rows_says_its_empty_line_and_still_draws_its_slot', () => {
  const view = draw([])
  expect(view.text()).toContain('Nobody is working')
  expect(view.find('tbody tr').exists()).toBe(false)
  expect(view.find('[data-extra]').text()).toBe('Idle: builder')
})

test('a_group_with_rows_draws_its_slot_after_them', () => {
  const view = draw([teamRow()])
  expect(view.text()).not.toContain('Nobody is working')
  expect(view.find('[data-extra]').exists()).toBe(true)
})

test('a_group_marks_only_the_selected_row_as_pressed', () => {
  const view = draw([teamRow({ key: 'a' }), teamRow({ key: 'b' })], undefined, 'b')
  expect(
    view.findAll('tbody tr button').map((button) => button.attributes('aria-pressed')),
  ).toEqual(['false', 'true'])
})

test('selecting_a_row_of_a_group_names_its_key', async () => {
  const view = draw([teamRow({ key: 'a' }), teamRow({ key: 'b' })])
  await view.findAll('tbody tr button')[1]?.trigger('click')
  expect(view.emitted('select')).toEqual([['b']])
})

test('a_group_holding_more_rows_than_a_page_links_to_the_next_page_under_its_prefix', () => {
  const view = draw([teamRow()], 25)
  expect(view.find('nav[aria-label*="working"] a[href*="working_page=2"]').exists()).toBe(true)
})

// An agent row says which agent it is: the avatar is labelled with its role, and every agent kind,
// a reviewer among them, shows the one agent icon.
test('a_rows_actor_avatar_names_its_role', () => {
  const view = draw([
    teamRow({ key: 'a', actor: { kind: 'reviewer', name: 'reviewer' } }),
    teamRow({ key: 'b', actor: { kind: 'agent', name: 'builder' } }),
    teamRow({ key: 'c', actor: { kind: 'owner', name: 'alex' } }),
  ])
  const avatars = view.findAll('[data-slot="avatar"]')

  expect(avatars.map((a) => a.attributes('aria-label'))).toEqual(['Review agent', 'Agent', 'You'])
  expect(avatars.map((a) => a.text())).toEqual(['', '', 'AL'])
  expect(avatars.slice(0, 2).map((a) => draws(a.element.querySelector('svg'), BotIcon))).toEqual([
    true,
    true,
  ])
})

test('a_group_lays_its_rows_out_by_its_own_width', () => {
  const view = draw([teamRow({ key: 'b' }), teamRow({ key: 'a' })])
  const table = view.get('table')
  expect(table.element.closest('.\\@container')).not.toBeNull()
  expect(table.classes()).toContain('@3xl:table-fixed')
  expect(view.findAll('thead th').map((cell) => cell.text())).toEqual([
    'Status',
    'Ticket',
    'Title',
    'Actor',
    'Activity',
    'Pull request',
    'Age',
  ])
  expect(view.findAll('tbody tr').map((row) => row.attributes('data-row'))).toEqual(['b', 'a'])
})
