import { expect, test } from 'vitest'
import { teamRow } from '../test/team'
import {
  MILESTONE_LABELS,
  STAGE_LABELS,
  against,
  alsoLine,
  bar,
  noStageTimes,
  peekKey,
  pullDot,
  pullWords,
  rowLine,
  type Also,
  type StageTimes,
} from './teamNow'

process.env.TZ = 'UTC'

const NOW = 1_794_312_000 // 2026-11-10 12:00:00 UTC
const pull = (gate: 'passed' | 'failed' | 'running' | 'not_run', merge: 'open' | 'conflict') => ({
  number: 20,
  url: 'https://example.test/pull/20',
  gate,
  merge,
})
const also = (state: Also['state'], kind: Also['actor']['kind'], name: string, line: string) => ({
  state,
  actor: { kind, name },
  line,
  since: NOW - 50 * 86_400,
  until: null,
})
const stage = (stage: StageTimes['stage'], today: number, cycle: number): StageTimes => ({
  stage,
  today: { median: today ? 60 : null, count: today },
  cycle: { median: cycle ? 60 : null, count: cycle },
})

// CF-1209: the process has no gate since 2026-11-10; the milestone is the first passing checks run.
test('the_milestone_and_a_pull_request_name_the_checks', () => {
  expect(STAGE_LABELS.gate_pass).toBe('to checks pass')
  expect(MILESTONE_LABELS.gate_pass).toBe('Checks pass')
  expect(
    (['passed', 'failed', 'running', 'not_run'] as const).map((g) => pullWords(pull(g, 'open'))),
  ).toEqual(['checks passed', 'checks failed', 'checks running', 'checks not run'])
  expect(pullWords(pull('passed', 'conflict'))).toBe('conflict')
})

// CF-1209: a ticket's other state as its row's second line: the state, its age, who and what.
test('a_second_line_says_the_other_state_its_age_and_what', () => {
  expect(alsoLine(also('stale', 'owner', 'you', 'agent failed (exit 1)'), NOW)).toBe(
    'also stale 50d: agent failed (exit 1)',
  )
  expect(
    alsoLine({ ...also('working', 'agent', 'builder', 'build run'), since: NOW - 540 }, NOW),
  ).toBe('also working 9m: builder, build run')
  expect(alsoLine({ ...also('waiting', 'gate', 'gate', ''), since: NOW - 30 }, NOW)).toBe(
    'also waiting 30s: gate',
  )
  expect(alsoLine({ ...also('owner', 'owner', 'you', ''), since: NOW - 7200 }, NOW)).toBe(
    'also waiting on you 2h',
  )
})

// CF-1209: the strip is one line only while no stage has a ticket today or this cycle.
test('the_strip_has_nothing_to_show_only_without_any_ticket', () => {
  const stages = (today: number, cycle: number) => [
    stage('first_commit', 0, 0),
    stage('pull_request', 0, 0),
    stage('gate_pass', 0, 0),
    stage('merged', today, cycle),
  ]
  expect(noStageTimes(stages(0, 0))).toBe(true)
  expect(noStageTimes(stages(0, 1))).toBe(false)
  expect(noStageTimes(stages(1, 1))).toBe(false)
})

// The strip's bar: both lengths are percents of one scale, 1.25 times the longer of the two.
test('a_bar_is_a_percent_of_one_and_a_quarter_times_the_longer', () => {
  expect(bar(30, 60)).toEqual({ fill: 40, mark: 80 })
  expect(bar(100, 50)).toEqual({ fill: 80, mark: 40 })
  expect(bar(60, 60)).toEqual({ fill: 80, mark: 80 })
})

test('a_bar_without_a_median_has_no_mark_and_without_today_no_fill', () => {
  expect(bar(60, null)).toEqual({ fill: 80, mark: 0 })
  expect(bar(null, 60)).toEqual({ fill: 0, mark: 80 })
})

test('a_bar_with_nothing_to_measure_is_empty', () => {
  expect(bar(null, null)).toEqual({ fill: 0, mark: 0 })
  expect(bar(0, 0)).toEqual({ fill: 0, mark: 0 })
})

// A row says what it does; a done row says when it merged first.
test('a_row_that_is_not_done_says_only_its_line', () => {
  expect(rowLine(teamRow({ state: 'working', line: 'build run' }))).toBe('build run')
  expect(rowLine(teamRow({ state: 'owner', line: 'asks a question', until: NOW }))).toBe(
    'asks a question',
  )
  expect(rowLine(teamRow({ state: 'stale', line: 'agent failed (exit 1)' }))).toBe(
    'agent failed (exit 1)',
  )
  expect(rowLine(teamRow({ state: 'waiting', line: 'review pickup' }))).toBe('review pickup')
})

test('a_done_row_says_when_it_merged_then_its_line', () => {
  expect(rowLine(teamRow({ state: 'merged', line: 'builder', until: NOW }))).toBe(
    'merged at 12:00, builder',
  )
  expect(rowLine(teamRow({ state: 'merged', line: 'builder', until: NOW - 33_300 }))).toBe(
    'merged at 02:45, builder',
  )
})

test('a_done_row_without_a_line_says_only_when_it_merged', () => {
  expect(rowLine(teamRow({ state: 'merged', line: '', until: NOW }))).toBe('merged at 12:00')
})

test('a_done_row_without_a_finish_says_only_its_line', () => {
  expect(rowLine(teamRow({ state: 'merged', line: 'builder', until: null }))).toBe('builder')
})

test('a_second_line_for_a_merged_state_names_no_actor_and_says_when_it_merged', () => {
  const merged: Also = {
    ...also('merged', 'agent', 'builder', 'shipped'),
    since: NOW - 3600,
    until: NOW,
  }
  expect(alsoLine(merged, NOW)).toBe('also merged 1h: merged at 12:00, shipped')
})

test('a_second_line_with_nothing_to_add_ends_after_the_age', () => {
  expect(alsoLine({ ...also('working', 'owner', 'you', ''), since: NOW - 60 }, NOW)).toBe(
    'also working 1m',
  )
})

// Today's median against the cycle's: a gap under one second is no gap.
test('today_against_the_cycle_says_how_far_over_or_under', () => {
  expect(against(660, 180)).toBe('8m over')
  expect(against(60, 240)).toBe('3m under')
})

test('today_against_the_cycle_is_on_it_below_one_second_apart', () => {
  expect(against(60, 60)).toBe('on the cycle median')
  expect(against(60.5, 60)).toBe('on the cycle median')
  expect(against(59.5, 60)).toBe('on the cycle median')
})

test('today_against_the_cycle_is_over_or_under_from_one_second_apart', () => {
  expect(against(61, 60)).toBe('1s over')
  expect(against(59, 60)).toBe('1s under')
})

test('today_against_the_cycle_says_nothing_while_either_is_unknown', () => {
  expect(against(null, 60)).toBe('')
  expect(against(60, null)).toBe('')
  expect(against(null, null)).toBe('')
})

test('a_pull_request_says_its_merge_state_before_its_checks', () => {
  expect(pullWords({ ...pull('failed', 'open'), merge: 'merged' })).toBe('merged')
  expect(pullWords(pull('failed', 'conflict'))).toBe('conflict')
  expect(pullWords(pull('not_run', 'open'))).toBe('checks not run')
})

test('a_pull_request_dot_is_primary_when_merged_or_passing', () => {
  expect(pullDot({ ...pull('failed', 'open'), merge: 'merged' })).toBe('bg-primary')
  expect(pullDot({ ...pull('running', 'open'), merge: 'merged' })).toBe('bg-primary')
  expect(pullDot(pull('passed', 'open'))).toBe('bg-primary')
})

test('a_pull_request_dot_is_destructive_on_a_conflict_or_failing_checks', () => {
  expect(pullDot(pull('passed', 'conflict'))).toBe('bg-destructive')
  expect(pullDot(pull('running', 'conflict'))).toBe('bg-destructive')
  expect(pullDot(pull('failed', 'open'))).toBe('bg-destructive')
})

test('a_pull_request_dot_is_muted_while_checks_run_and_fainter_before_they_do', () => {
  expect(pullDot(pull('running', 'open'))).toBe('bg-muted-foreground')
  expect(pullDot(pull('not_run', 'open'))).toBe('bg-muted-foreground/30')
})

test('a_ticket_peek_is_found_by_repository_and_id', () => {
  expect(peekKey(teamRow())).toBe('sample/CF-1')
  expect(peekKey(teamRow({ ticket: null }))).toBe('')
})
