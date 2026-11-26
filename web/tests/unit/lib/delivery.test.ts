// What a card says about where its delivery stands, one case per status it can show.

import { describe, expect, test } from 'vitest'
import { goldenBoard } from '../../support/board'
import { present } from '../../support/present'
import type { Card } from '@/lib/board'
import { deliveryStatus } from '@/lib/delivery'

const base: Card = {
  ...present(goldenBoard().columns.build[0], 'a card'),
  stage: 'build',
  archived: false,
  open_questions: 0,
  runs: [],
  pull: null,
  check: null,
}
delete base.holder
delete base.queue
delete base.delivery_event
delete base.checks_configured

const card = (change: Partial<Card>): Card => ({ ...base, ...change })
const run = {
  id: 'r',
  stage: 'build',
  iteration: 1,
  loop: false,
  max_iterations: 1,
  attempt: 0,
} as const
const pull = { state: 'open', ci: 'success', head: 'h', url: 'u', at: '100' }
const event = (kind: NonNullable<Card['delivery_event']>['kind'], retry: number | null = null) => ({
  kind,
  at: 50,
  retry_at: retry,
})

describe('deliveryStatus', () => {
  test('merged_released_and_archived_cards_say_nothing', () => {
    expect(deliveryStatus(card({ stage: 'merged' }))).toBeNull()
    expect(deliveryStatus(card({ stage: 'released' }))).toBeNull()
    expect(deliveryStatus(card({ archived: true }))).toBeNull()
  })

  test('an_open_question_waits_for_an_answer_before_anything_else', () => {
    const status = deliveryStatus(card({ open_questions: 1, runs: [{ ...run, agent: 'codex' }] }))
    expect(status).toEqual({ label: 'Waiting for an answer' })
  })

  test('a_run_names_its_agent_and_stage_and_when_it_started', () => {
    expect(deliveryStatus(card({ runs: [{ ...run, agent: 'codex', started_at: 7 }] }))).toEqual({
      label: 'codex · Build',
      state: 'working',
      since: 7,
    })
  })

  test('a_run_without_an_agent_falls_back_to_the_holder_then_to_agent', () => {
    expect(deliveryStatus(card({ holder: 'alex', runs: [{ ...run, agent: '' }] }))?.label).toBe(
      'alex · Build',
    )
    expect(deliveryStatus(card({ runs: [run] }))).toEqual({
      label: 'Agent · Build',
      state: 'working',
    })
  })

  test('a_holder_without_a_run_is_working', () => {
    expect(deliveryStatus(card({ holder: 'alex' }))).toEqual({
      label: 'alex working',
      state: 'working',
    })
  })

  test('a_merged_or_closed_pull_request_says_nothing', () => {
    expect(deliveryStatus(card({ pull: { ...pull, state: 'merged' } }))).toBeNull()
    expect(deliveryStatus(card({ pull: { ...pull, state: 'closed' } }))).toBeNull()
  })

  test('a_failed_ship_or_merge_says_failed_or_when_it_is_retried', () => {
    expect(deliveryStatus(card({ delivery_event: event('ship_failed') }))).toEqual({
      label: 'Ship failed',
    })
    expect(deliveryStatus(card({ delivery_event: event('merge_failed', 90) }))).toEqual({
      label: 'Merge interrupted',
      retryAt: 90,
    })
  })

  test('a_ship_in_progress_says_its_step_since_the_event', () => {
    expect(deliveryStatus(card({ delivery_event: event('ship_started') }))).toEqual({
      label: 'Shipping branch',
      since: 50,
    })
    expect(deliveryStatus(card({ delivery_event: event('ship_pushed') }))).toEqual({
      label: 'Opening pull request',
      since: 50,
    })
  })

  test('an_open_pull_request_with_a_conflict_says_so_and_a_draft_says_nothing', () => {
    expect(deliveryStatus(card({ pull: { ...pull, conflict: true, draft: true } }))).toEqual({
      label: 'Merge conflict',
    })
    expect(deliveryStatus(card({ pull: { ...pull, draft: true } }))).toBeNull()
  })

  test('failed_checks_on_the_board_or_elsewhere_say_checks_failed', () => {
    expect(deliveryStatus(card({ pull, check: { passed: false, commit: 'h' } }))).toEqual({
      label: 'Checks failed',
    })
    expect(deliveryStatus(card({ pull: { ...pull, ci: 'failed' } }))).toEqual({
      label: 'Checks failed',
    })
    expect(
      deliveryStatus(card({ pull: { ...pull, ci: 'failed', other_ci: 'success' } })),
    ).toBeNull()
  })

  test('pending_checks_wait_since_the_pull_request_entered', () => {
    expect(deliveryStatus(card({ pull: { ...pull, ci: 'pending', since: '80' } }))).toEqual({
      label: 'Waiting for checks',
      since: 80,
    })
    expect(deliveryStatus(card({ pull, checks_configured: true }))).toEqual({
      label: 'Waiting for checks',
      since: 100,
    })
    expect(deliveryStatus(card({ pull }))).toBeNull()
  })

  test('a_card_next_in_the_queue_is_queued_for_an_agent', () => {
    expect(deliveryStatus(card({ queue: 'next' }))).toEqual({ label: 'Queued for an agent' })
    expect(deliveryStatus(card({ queue: 'Build 1 of 1' }))).toBeNull()
    expect(deliveryStatus(card({}))).toBeNull()
  })
})
