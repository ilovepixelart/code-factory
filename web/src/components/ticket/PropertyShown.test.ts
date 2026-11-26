// @vitest-environment happy-dom
// A property of a ticket being edited is quiet until it is changed (components/ticket/PropertyShown.vue).

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, test } from 'vitest'
import { h } from 'vue'
import PropertyShown from './PropertyShown.vue'

afterEach(() => {
  document.body.innerHTML = ''
})

const row = (props: Record<string, unknown>) =>
  mount(PropertyShown, {
    attachTo: document.body.appendChild(document.createElement('div')),
    props: { id: 'CF-1-assignee', label: 'Assignee', value: '', empty: 'unassigned', ...props },
    slots: { default: () => h('input', { id: 'CF-1-assignee', 'aria-label': 'Assignee' }) },
  })

const shown = (view: ReturnType<typeof row>) => ({
  quiet: view.get('[data-property-shown]').isVisible(),
  control: view.get('[data-property-editing]').isVisible(),
})

test('a_quiet_row_shows_its_value_and_hides_its_control', () => {
  const set = row({ value: 'alex' })
  const empty = row({})

  expect([
    shown(set),
    set.get('button').text(),
    empty.get('button').text(),
    empty.get('button span').classes(),
  ]).toEqual([
    { quiet: true, control: false },
    'alex',
    'unassigned',
    ['truncate', 'text-muted-foreground'],
  ])
})

test('pressing_the_row_shows_its_control_with_the_focus', async () => {
  const view = row({ value: 'alex' })

  await view.get('button').trigger('click')
  await flushPromises()

  expect([shown(view), document.activeElement?.id]).toEqual([
    { quiet: false, control: true },
    'CF-1-assignee',
  ])
})

test('escape_puts_the_row_back_to_quiet', async () => {
  const view = row({ value: 'alex' })
  await view.get('button').trigger('click')
  await flushPromises()

  await view.get('#CF-1-assignee').trigger('keydown', { key: 'Escape' })

  expect(shown(view)).toEqual({ quiet: true, control: false })
})

test('a_refused_value_keeps_its_control_open', () => {
  expect(shown(row({ value: 'x', invalid: true }))).toEqual({ quiet: false, control: true })
})

test('a_read_only_row_shows_its_value_without_a_button', () => {
  const view = row({ value: 'gh:42', readonly: true, code: true })

  expect([view.find('button').exists(), view.get('#CF-1-assignee-shown').text()]).toEqual([
    false,
    'gh:42',
  ])
})
