import { expect, test } from 'vitest'
import { dropBlankTitle, fieldsOf } from './ticket'

test('fields_of_sends_every_field', () => {
  const ticket = {
    id: 'CF-2',
    title: 'Bare',
    type: 'bug',
    branch: 'b',
    e2e: 'e',
    tests: 't',
    description: 'd',
    stage: 'brd',
    labels: 'x, y',
    priority: 'high',
    assignee: 'al',
    due: '2026-11-01',
    blocked: 'w',
    archived: true,
    rank: 3,
    stage_since: 's',
    blocked_by: 'CF-1',
    parent: 'CF-3',
    budget: '2',
    parallel: '3',
    source: 'src',
    pages: '/p',
    caused_by: 'CF-9',
  }

  expect(Object.entries(fieldsOf(ticket))).toEqual([
    ['title', 'Bare'],
    ['description', 'd'],
    ['stage', 'brd'],
    ['type', 'bug'],
    ['priority', 'high'],
    ['due', '2026-11-01'],
    ['labels', 'x, y'],
    ['assignee', 'al'],
    ['blocked', 'w'],
    ['blocked_by', 'CF-1'],
    ['parent', 'CF-3'],
    ['branch', 'b'],
    ['e2e', 'e'],
    ['tests', 't'],
    ['pages', '/p'],
    ['caused_by', 'CF-9'],
    ['budget', '2'],
    ['parallel', '3'],
  ])
})

test('a_save_sends_only_the_changed_fields', () => {
  const loaded = { title: 'Bare', branch: '', priority: 'high', parent: 'CF-3' }

  expect(fieldsOf({ ...loaded, title: 'Renamed' }, loaded)).toEqual({ title: 'Renamed' })
  expect(fieldsOf({ ...loaded }, loaded)).toEqual({})
})

test.each([
  ['empty', '', true],
  ['whitespace', ' \t ', true],
  ['text', ' Fix it ', false],
])('a_%s_title_is_blank_or_not', (_name, title, blank) => {
  const changed: Record<string, string> = { title, budget: '3' }

  expect(dropBlankTitle(changed)).toBe(blank)
  expect(changed).toEqual(blank ? { budget: '3' } : { title, budget: '3' })
})

test('a_save_without_a_title_has_no_blank_title', () => {
  const changed = { budget: '3' }

  expect(dropBlankTitle(changed)).toBe(false)
  expect(changed).toEqual({ budget: '3' })
})
