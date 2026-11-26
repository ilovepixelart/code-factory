// The page anatomy of docs/design.md, held over every template outside components/ui: a section
// is a SectionCard (the one composition of a Card's parts), a list section carries its count, and
// an Empty sits in a SectionCard's `empty` slot, at the top of its Card. A file that breaks a rule
// for a reason is listed with it, and the list only shrinks (test/guard.ts).

import { describe, expect, test } from 'vitest'
import { offenders, readVue, sourceOffenders, verdict, vueFiles } from './test/guard'

const OURS = vueFiles().filter((file) => !file.startsWith('components/ui/'))
const SECTION = 'components/SectionCard.vue'

/** The Cards that are not a page's section: each is its own surface, in no section's Card. */
const CARDS: Record<string, string> = {
  'components/SignInNotice.vue': "the signed-out screen, login-03's one Card",
  'components/TicketCard.vue': "a ticket on the board, the board's own surface",
  'components/ContentCard.vue': 'one record in a spaced list, such as a Memory entry',
  'components/flow/FlowTiles.vue': "dashboard-01's section cards, one figure each",
  'components/flow/HeldTiles.vue': "dashboard-01's section cards, one figure each",
  'components/flow/OutcomeTiles.vue': "dashboard-01's section cards, one figure each",
  'components/factory/FactoryTiles.vue': "dashboard-01's section cards, one figure each",
  'components/flow/PullsChart.vue': "ChartAreaInteractive's Card, the chart's own surface",
  'pages/ReplyPage.vue': 'the reply page stands alone, outside the shell: its Card is the page',
}

/** The Empty states that are a line inside a control or a form, not a section's state. */
const INLINE_EMPTIES: Record<string, string> = {
  'components/AgentContextField.vue': "the preview tab's line before anything is written",
  'components/TicketForm.vue': "the description preview's line before anything is written",
  'components/CommandMenu.vue': "the command list's line when nothing matches",
  'components/TicketChanges.vue': 'the line of a branch with no changes, under its section title',
  'components/ticket/TicketAgent.vue': "the agent block's line in the ticket form",
  'components/ticket/TicketLinks.vue': "the links block's line in the ticket form",
  'components/ticket/TicketScreens.vue': "the screens block's state in the ticket form",
  'pages/TicketsPage.vue': "the board's loading state, which Skeletons replace",
  'pages/TicketPage.vue': 'a ticket that does not exist, the whole page',
  'pages/SessionPage.vue': 'a session that does not exist, the whole page',
  'pages/design/DesignComponents.vue': 'the samples of every empty state',
  'pages/design/DesignStates.vue': 'the sample of an empty state',
  'components/flow/PullsChart.vue': "the chart Card's own state for a quiet range",
}

/** The source with each SectionCard `empty` slot taken out. */
const withoutEmptySlots = (source: string): string =>
  source.replace(/<template #empty\s*>[\s\S]*?<\/template\s*>/g, '')

/** The SectionCards that hold a list or a table and show no count. */
function uncounted(source: string): string[] {
  return [...source.matchAll(/<SectionCard\b([^>]*)>([\s\S]*?)<\/SectionCard>/g)]
    .filter(
      ([, open = '', inside = '']) =>
        /<(ItemGroup|Table)\b/.test(inside) && !open.includes(':count'),
    )
    .map(([, open = '']) => /heading="([^"]+)"/.exec(open)?.[1] ?? 'a section')
}

describe('the page anatomy', () => {
  test('every_card_is_a_section_card_or_a_listed_surface', () => {
    const found = offenders(OURS, (tag) => tag.name === 'Card', [SECTION])

    expect(found.size).toBeGreaterThan(0)
    expect(verdict(found, CARDS)).toEqual([])
  })

  test('every_empty_state_sits_in_its_section_card', () => {
    const found = sourceOffenders(OURS, (source) =>
      /<Empty(?=[\s>])/.test(withoutEmptySlots(source)),
    )

    expect(verdict(found, INLINE_EMPTIES)).toEqual([])
  })

  test('a_section_that_lists_shows_its_count', () => {
    // The /design samples show components, not a list of the board's records.
    const found = OURS.filter((file) => !file.startsWith('pages/design/')).flatMap((file) =>
      uncounted(readVue(file)).map((id) => `${file}: ${id}`),
    )

    expect(found).toEqual([])
  })
})

describe('the anatomy rules flag the breach and pass the correct form', () => {
  test('an_empty_outside_the_slot_is_found', () => {
    expect(
      [
        '<SectionCard heading="a" title="A" empty><template #empty><Empty /></template></SectionCard>',
        '<SectionCard heading="a" title="A"><Empty /></SectionCard>',
      ].map((source) => /<Empty(?=[\s>])/.test(withoutEmptySlots(source))),
    ).toEqual([false, true])
  })

  test('a_list_without_its_count_is_found', () => {
    expect([
      uncounted('<SectionCard heading="a" title="A"><ItemGroup /></SectionCard>'),
      uncounted('<SectionCard heading="b" title="B" :count="n"><Table /></SectionCard>'),
      uncounted('<SectionCard heading="c" title="C"><p>prose</p></SectionCard>'),
    ]).toEqual([['a'], [], []])
  })
})
