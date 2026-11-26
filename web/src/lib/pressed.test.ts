// Of several buttons sharing one busy state, only the one pressed shows its Spinner, and only
// while the busy state holds.

import { describe, expect, test } from 'vitest'
import { usePressed } from './pressed'

describe('the pressed button', () => {
  test('only_the_pressed_button_spins_while_busy', () => {
    const { press, spins } = usePressed()

    press('archive', () => undefined)

    expect([spins('archive', true), spins('delete', true)]).toEqual([true, false])
  })

  test('no_button_spins_once_the_busy_state_ends', () => {
    const { press, spins } = usePressed()

    press('archive', () => undefined)

    expect(spins('archive', false)).toBe(false)
  })

  test('press_runs_the_action_and_returns_its_result', () => {
    const { press } = usePressed()

    expect(press('answer', () => 42)).toBe(42)
  })

  test('a_promise_clears_the_press_as_it_ends_so_a_later_busy_state_shows_no_spinner', async () => {
    const { press, spins } = usePressed()
    let finish = (): void => undefined
    const sent = press('start', () => new Promise<void>((resolve) => (finish = resolve)))

    const during = spins('start', true)
    finish()
    await sent
    await Promise.resolve()

    expect([during, spins('start', true)]).toEqual([true, false])
  })

  test('a_refused_promise_also_clears_the_press', async () => {
    const { press, spins } = usePressed()

    await press('start', () => Promise.reject(new Error('refused'))).catch(() => undefined)
    await Promise.resolve()

    expect(spins('start', true)).toBe(false)
  })

  test('a_later_press_takes_the_spinner_and_an_earlier_promise_ending_leaves_it', async () => {
    const { press, spins } = usePressed()
    let finish = (): void => undefined
    const first = press('approve', () => new Promise<void>((resolve) => (finish = resolve)))
    press('dismiss', () => undefined)

    finish()
    await first
    await Promise.resolve()

    expect([spins('approve', true), spins('dismiss', true)]).toEqual([false, true])
  })
})
