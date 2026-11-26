// CF-321: the helpers the components share, each written once.

import { describe, expect, test } from 'vitest'
import { Refused } from '@/lib/actions'
import { spendLevel } from '@/lib/format'
import { refusalText } from '@/lib/notice'
import { ticketHref } from '@/lib/ticket'

describe('shared helpers', () => {
  test('a_ticket_address_encodes_its_parts', () => {
    expect(ticketHref('sample', 'CF-1')).toBe('/tickets/sample/CF-1')
    expect(ticketHref('r#x', 'CF 2')).toBe('/tickets/r%23x/CF%202')
  })

  test('a_refusal_reads_as_its_reason_or_that_the_board_did_not_answer', () => {
    expect(refusalText(new Refused('no ticket CF-9'))).toBe('no ticket CF-9')
    expect(refusalText(new TypeError('Failed to fetch'))).toBe(
      'The board did not answer; try again.',
    )
  })

  test('spend_is_over_at_the_budget_and_watched_from_four_fifths', () => {
    expect(spendLevel(5, null)).toBe('normal')
    expect(spendLevel(7.99, 10)).toBe('normal')
    expect(spendLevel(8, 10)).toBe('watch')
    expect(spendLevel(9.99, 10)).toBe('watch')
    expect(spendLevel(10, 10)).toBe('over')
  })
})
