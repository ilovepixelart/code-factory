// @vitest-environment happy-dom
// A card's delivery chip takes its colour from the status map, as every other status badge does:
// a failure in the error badge, what waits on the owner in warning, what is under way in info.

import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import type { Card } from '../lib/board'
import { TONE_VARIANTS } from '../lib/status_tone'
import { goldenBoard } from '../test/board'
import { present } from '../test/present'
import DeliveryStatus from './DeliveryStatus.vue'

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

const chip = (change: Partial<Card>) => {
  const badge = mount(DeliveryStatus, { props: { card: { ...base, ...change } } }).get(
    '[data-slot="badge"]',
  )
  return [badge.text(), badge.attributes('data-variant')]
}
const pull = { state: 'open', ci: 'success', head: 'h', url: 'u', at: '100' } as const
const run = { id: 'r', stage: 'build', iteration: 1, loop: false, max_iterations: 1, attempt: 0 }

test.each([
  [
    'a_failed_ship',
    { delivery_event: { kind: 'ship_failed', at: 5, retry_at: null } },
    'Ship failed',
    TONE_VARIANTS.error,
  ],
  ['an_open_question', { open_questions: 1 }, 'Waiting for an answer', TONE_VARIANTS.warning],
  [
    'pending_checks',
    { pull: { ...pull, ci: 'pending' } },
    'Waiting for checks',
    TONE_VARIANTS.info,
  ],
  ['a_conflict', { pull: { ...pull, conflict: true } }, 'Merge conflict', TONE_VARIANTS.warning],
  ['a_run', { runs: [{ ...run, agent: 'codex' }] }, 'codex · Build', TONE_VARIANTS.info],
] as [string, Partial<Card>, string, string][])(
  '%s_shows_its_words_in_its_tone',
  (_, change, words, variant) => {
    expect(chip(change)).toEqual([words, variant])
  },
)
