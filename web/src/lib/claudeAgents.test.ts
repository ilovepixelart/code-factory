import { expect, test } from 'vitest'
import type { ClaudeAgent } from '../generated/ClaudeAgent'
import { overriddenBy } from './claudeAgents'

const file = (name: string, place: string): ClaudeAgent => ({
  name,
  description: '',
  model: '',
  tools: [],
  place,
  path: `/${place}/${name}.md`,
})

test('a_project_copy_wins_over_the_global_one_of_the_same_name', () => {
  const listed = [file('ticket-worker', 'global'), file('ticket-worker', 'repo')]

  expect(overriddenBy(listed)).toStrictEqual({ '/global/ticket-worker.md': 'repo' })
})

test('the_closest_project_copy_wins_over_one_further_up', () => {
  const listed = [file('a', 'global'), file('a', 'worktree'), file('a', 'repo')]

  expect(overriddenBy(listed)).toStrictEqual({
    '/global/a.md': 'worktree',
    '/repo/a.md': 'worktree',
  })
})

test('an_agent_with_no_copy_is_overridden_by_nothing', () => {
  const listed = [file('a', 'global'), file('b', 'repo')]

  expect(overriddenBy(listed)).toStrictEqual({})
})
