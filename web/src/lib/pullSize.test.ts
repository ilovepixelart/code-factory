// A pull request's size and whether it is past what a review reads well (docs/ui.md, The kanban).

import { expect, test } from 'vitest'
import { LARGE_PULL_LINES, pullSize } from './pullSize'

const pull = (size: Partial<{ additions: number; deletions: number; changed_files: number }>) => ({
  state: 'open',
  ci: 'none',
  head: 'h',
  url: 'u',
  at: '0',
  ...size,
})

test('a_size_is_its_lines_added_and_removed_and_its_files', () => {
  expect(pullSize(pull({ additions: 86, deletions: 12, changed_files: 4 }))).toEqual({
    added: 86,
    removed: 12,
    files: 4,
    lines: 98,
    large: false,
  })
})

test.each([
  [400, 0, false],
  [300, 100, false],
  [401, 0, true],
  [1240, 380, true],
])('%i_added_and_%i_removed_is_large_%s', (additions, deletions, large) => {
  expect(pullSize(pull({ additions, deletions, changed_files: 1 }))?.large).toBe(large)
})

test('the_bound_is_four_hundred_lines', () => {
  expect(LARGE_PULL_LINES).toBe(400)
})

test('a_pull_request_without_a_count_has_no_size', () => {
  expect([pullSize(pull({})), pullSize(pull({ additions: 5 })), pullSize(null)]).toEqual([
    null,
    null,
    null,
  ])
})
