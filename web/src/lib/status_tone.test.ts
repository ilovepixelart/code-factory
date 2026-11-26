import { expect, test } from 'vitest'
import { PULL_STATES } from './pull_state'
import { statusTone, statusVariant, TONE_VARIANTS } from './status_tone'

// One semantic tone per status word: success for what is done, info for what is under way,
// warning for what waits on someone, error for what failed, quiet for what is at rest.
test.each([
  ['finished', 'success'],
  ['done', 'success'],
  ['approved', 'success'],
  ['merged', 'success'],
  ['working', 'info'],
  ['running', 'info'],
  ['open', 'info'],
  ['checks running', 'info'],
  ['waiting', 'warning'],
  ['owner', 'warning'],
  ['blocked', 'warning'],
  ['stale', 'warning'],
  ['uncommitted', 'warning'],
  ['conflict', 'warning'],
  ['failed', 'error'],
  ['denied', 'error'],
  ['checks failing', 'error'],
  ['idle', 'quiet'],
  ['stopped', 'quiet'],
  ['closed', 'quiet'],
  ['ended', 'quiet'],
  ['draft', 'quiet'],
])('the_word_%s_takes_the_%s_tone', (word, tone) => {
  expect(statusTone(word)).toBe(tone)
})

test('a_word_nobody_named_takes_the_quiet_tone', () => {
  expect(statusTone('something else')).toBe('quiet')
})

// Each coloured tone has a Badge variant of its own colour, never a solid fill; error is shadcn's
// destructive badge and quiet the outline.
test('each_tone_draws_with_its_own_badge_variant', () => {
  expect(TONE_VARIANTS).toEqual({
    success: 'success',
    info: 'info',
    warning: 'warning',
    error: 'destructive',
    quiet: 'outline',
  })
})

// A pull request's label wears its state's colour: merged in success, open in info, failing checks
// in the error badge (CF-1217).
test('a_pull_request_label_takes_its_state_colour', () => {
  expect([PULL_STATES.merged, PULL_STATES.open, PULL_STATES['checks failing']]).toEqual([
    { words: 'Merged', variant: 'success' },
    { words: 'Open', variant: 'info' },
    { words: 'Checks failing', variant: 'destructive' },
  ])
  expect(statusVariant('merged')).toBe('success')
})
