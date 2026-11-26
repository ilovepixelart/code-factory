import { expect, test } from 'vitest'
import { keepPresent } from './selection'

test('keep_present_drops_cards_that_left', () => {
  const chosen = new Set(['sample/CF-2', 'second/CF-1', 'sample/CF-9'])

  keepPresent(chosen, ['sample/CF-1', 'sample/CF-2', 'second/CF-1'])

  expect([...chosen]).toEqual(['sample/CF-2', 'second/CF-1'])
})
