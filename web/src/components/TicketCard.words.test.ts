// @vitest-environment happy-dom
// What a card says must read without knowing the board's internals: no fact twice, no shorthand.

import { mount } from '@vue/test-utils'
import { describe, expect, test } from 'vitest'
import type { Card } from '../lib/board'
import { goldenBoard, memoryRouter, provideBoard } from '../test/board'
import { present } from '../test/present'
import TicketCard from './TicketCard.vue'

const board = goldenBoard()
const base = present(board.columns.spec[0], 'a card')

const text = (overrides: Partial<Card>): string => {
  const card: Card = { ...base, ...overrides }
  return mount(TicketCard, {
    props: { card, stage: card.stage, today: board.today },
    global: { plugins: [memoryRouter()], provide: provideBoard(board), stubs: { CardMenu: true } },
  })
    .text()
    .replace(/\s+/g, ' ')
}

describe('a card says each fact once, in words', () => {
  test('open_questions_show_once', () => {
    const said = text({ open_questions: 1, runs: [] })

    expect(said).toContain('1 open question')
    expect(said).not.toContain('Waiting for an answer')
  })

  test('days_in_the_column_name_the_column', () => {
    expect(
      text({ stage: 'build', declared: 'build', evidence_stage: 'build', days_in_column: 3 }),
    ).toContain('3 days in Build')
    expect(
      text({ stage: 'build', declared: 'build', evidence_stage: 'build', days_in_column: 1 }),
    ).toContain('1 day in Build')
    const today = text({
      stage: 'build',
      declared: 'build',
      evidence_stage: 'build',
      days_in_column: 0,
    })
    expect(today).toContain('In Build since today')
    expect(today).not.toContain('0d here')
  })

  test('a_column_the_evidence_disagrees_with_says_what_git_shows', () => {
    const said = text({ stage: 'build', declared: 'build', evidence_stage: 'review' })

    expect(said).toContain('Git shows Review')
    expect(said).not.toContain('evidence:')
  })

  test('a_live_session_is_named_as_a_session', () => {
    const session = present(
      Object.values(board.columns)
        .flat()
        .flatMap((c) => c.sessions)
        .find((s) => s.state !== 'ended'),
      'a live session',
    )
    const said = text({ sessions: [session], open_questions: 0 })

    expect(said).toMatch(/session [0-9a-z-]+/)
  })

  test('a_checklist_and_children_are_named', () => {
    const said = text({
      checklist: [0, 3],
      links: { open_blockers: [], children: 2, children_done: 1 },
    })

    expect(said).toContain('Checklist 0/3')
    expect(said).toContain('Child tickets 1/2')
  })

  test('status_words_start_with_a_capital_as_the_delivery_status_does', () => {
    const said = text({
      blocked: 'waits for the vendor',
      archived: true,
      links: { open_blockers: ['CF-2'], children: 0, children_done: 0 },
    })

    expect(said).toContain('Blocked by CF-2')
    expect(said).toContain('Blocked: waits for the vendor')
    expect(said).toContain('Archived')
    expect(said).not.toMatch(/blocked|archived/)
  })
})
