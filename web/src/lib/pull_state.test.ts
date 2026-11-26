import { describe, expect, test } from 'vitest'
import type { Card } from './board'
import { pullState } from './pull_state'

type Input = Pick<Card, 'pull' | 'check'>
const pull = (over: Partial<NonNullable<Card['pull']>> = {}): Card['pull'] => ({
  state: 'open',
  ci: 'passed',
  head: 'h',
  url: 'https://example.invalid/pull/1',
  at: '1',
  ...over,
})
const of = (p: Card['pull'], check: Card['check'] = null): Input => ({ pull: p, check })

describe('pullState', () => {
  test('no_pull_request_has_no_label', () => {
    expect(pullState(of(null))).toBeNull()
  })
  test('a_closed_unmerged_pull_is_closed', () => {
    expect(pullState(of(pull({ state: 'closed' })))).toBe('closed')
  })
  test('closed_outranks_a_conflict_and_failing_checks', () => {
    expect(pullState(of(pull({ state: 'closed', conflict: true, ci: 'failed' })))).toBe('closed')
  })
  test('a_pull_in_an_unknown_state_has_no_label', () => {
    expect(pullState(of(pull({ state: 'unknown' })))).toBeNull()
  })
  test('an_open_pull_is_open', () => {
    expect(pullState(of(pull()))).toBe('open')
  })
  test('an_approved_open_pull_is_approved', () => {
    expect(pullState(of(pull({ review: 'approved' })))).toBe('approved')
  })
  test('a_draft_is_a_draft_even_when_approved', () => {
    expect(pullState(of(pull({ draft: true, review: 'approved' })))).toBe('draft')
  })
  test('failing_checks_outrank_a_draft', () => {
    expect(pullState(of(pull({ draft: true, ci: 'failed' })))).toBe('checks failing')
  })
  test('a_conflict_outranks_failing_checks', () => {
    expect(pullState(of(pull({ conflict: true, ci: 'failed' })))).toBe('conflict')
  })
  test('merged_outranks_a_conflict', () => {
    expect(pullState(of(pull({ state: 'merged', conflict: true, ci: 'failed' })))).toBe('merged')
  })
  // CF-1318: the board's failed checks are the card's text, so the label says the pull request's
  // own state.
  test('the_boards_own_failed_check_leaves_the_label_to_the_pull_request', () => {
    expect(pullState(of(pull(), { passed: false, commit: 'c' }))).toBe('open')
    expect(pullState(of(pull({ ci: 'failed' }), { passed: false, commit: 'c' }))).toBe('open')
    expect(pullState(of(pull({ draft: true }), { passed: false, commit: 'c' }))).toBe('draft')
  })
  test('the_boards_own_record_overrides_a_stale_failed_status', () => {
    expect(pullState(of(pull({ ci: 'failed' }), { passed: true, commit: 'c' }))).toBe('open')
  })
  test('without_the_boards_record_the_other_checks_decide', () => {
    expect(pullState(of(pull({ ci: 'failed', other_ci: 'passed' })))).toBe('open')
    expect(pullState(of(pull({ ci: 'passed', other_ci: 'failed' })))).toBe('checks failing')
  })
  test('pending_checks_are_running_not_failing', () => {
    expect(pullState(of(pull({ ci: 'pending' })))).toBe('checks running')
  })
  test('failing_checks_outrank_running_checks', () => {
    expect(pullState(of(pull({ ci: 'pending', other_ci: 'failed' })))).toBe('checks failing')
  })
  test('a_conflict_outranks_running_checks', () => {
    expect(pullState(of(pull({ ci: 'pending', conflict: true })))).toBe('conflict')
  })
  test('running_checks_outrank_a_draft_and_an_approval', () => {
    expect(pullState(of(pull({ ci: 'pending', draft: true })))).toBe('checks running')
    expect(pullState(of(pull({ ci: 'pending', review: 'approved' })))).toBe('checks running')
  })
  test('other_checks_pending_run_beside_the_boards_passed_record', () => {
    expect(
      pullState(of(pull({ ci: 'pending', other_ci: 'pending' }), { passed: true, commit: 'c' })),
    ).toBe('checks running')
  })
  test('the_boards_passed_record_ends_the_run_of_its_own_pending_status', () => {
    expect(
      pullState(of(pull({ ci: 'pending', other_ci: 'passed' }), { passed: true, commit: 'c' })),
    ).toBe('open')
  })
  test('without_the_boards_record_its_own_pending_status_is_a_running_check', () => {
    expect(pullState(of(pull({ ci: 'pending', other_ci: 'passed' })))).toBe('checks running')
  })
  test('passed_checks_are_not_running', () => {
    expect(pullState(of(pull({ ci: 'passed' })))).toBe('open')
  })
})
