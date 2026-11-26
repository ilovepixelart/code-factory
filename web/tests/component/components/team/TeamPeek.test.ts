// CF-1162: the peek of a ticket draws its milestones from filing against the cycle's medians, its
// last events and its links; below 1024 px it is a modal sheet.

import { mount } from '@vue/test-utils'
import { afterEach, expect, test, vi } from 'vitest'
import { memoryRouter } from '../../../support/board'
import { NOW, teamPeek, teamRow } from '../../../support/team'
import type { Peek } from '@/lib/teamNow'
import TeamPeek from '@/components/team/TeamPeek.vue'

process.env.TZ = 'UTC'

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

function narrow(matches: boolean): void {
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => ({
      matches,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
    })),
  )
}

const draw = (peek: Peek | undefined = teamPeek(), row = teamRow()) =>
  mount(TeamPeek, {
    props: { row, peek, now: NOW },
    global: { plugins: [memoryRouter()] },
    attachTo: document.body,
  })

const milestone = (view: ReturnType<typeof draw>, stage: string) =>
  view.get(`[data-milestone="${stage}"]`)

test('a_milestone_not_yet_reached_says_not_yet_and_how_long_since_filing', () => {
  const view = draw()
  expect(milestone(view, 'pull_request').text()).toContain('not yet · 2h so far')
})

test('a_reached_milestone_shows_its_time_and_its_span_after_filing_and_the_cycle_median', () => {
  const view = draw()
  const text = milestone(view, 'first_commit').text()
  expect(text).toContain('10:20 · 20m')
  expect(text).toContain('cycle 30m')
})

test('a_milestone_says_not_yet_alone_when_the_ticket_has_no_filing_time', () => {
  const peek = teamPeek()
  peek.milestones = [{ stage: 'first_commit', at: null, cycle: null }]
  expect(milestone(draw(peek), 'first_commit').text()).toContain('not yet')
  expect(milestone(draw(peek), 'first_commit').text()).not.toContain('so far')
})

test('a_milestone_bar_fills_to_its_span_and_marks_the_cycle_median_on_one_scale', () => {
  const bars = milestone(draw(), 'first_commit').findAll('span[style]')
  // 1200 s against a 1800 s median: the scale is 2250 s.
  expect(bars[0]?.attributes('style')).toMatch(/width: 53\.3/)
  expect(bars[1]?.attributes('style')).toMatch(/left: 80/)
})

test('the_filed_milestone_has_no_bar', () => {
  expect(milestone(draw(), 'filed').find('span[style]').exists()).toBe(false)
})

test('the_peek_lists_its_last_events_with_their_times', () => {
  const view = draw()
  const events = view.get('ol[aria-label="Last events"]').text()
  expect(events).toContain('11:55:00')
  expect(events).toContain('build run started')
})

test('the_peek_names_its_ticket_type_column_pull_request_and_line', () => {
  const view = draw(
    teamPeek(),
    teamRow({
      pull: { number: 20, url: 'https://example.test/pull/20', gate: 'failed', merge: 'open' },
    }),
  )
  expect(view.get('h3').text()).toBe('Build the thing')
  const line = view.get('p.text-muted-foreground').text().replace(/\s+/g, ' ')
  expect(line).toBe('Feature · Build · #20 checks failed · build run')
})

test('the_peek_links_to_its_ticket_and_its_activity', () => {
  const links = draw()
    .findAll('a')
    .map((a) => [a.text(), a.attributes('href')])
  expect(links).toContainEqual(['Open CF-1', '/tickets/sample/CF-1'])
  expect(links).toContainEqual(['All its activity', '/tickets/sample/CF-1#activity-heading'])
})

test('a_ticket_without_a_peek_draws_no_milestones', () => {
  const view = mount(TeamPeek, {
    props: { row: teamRow(), peek: undefined, now: NOW },
    global: { plugins: [memoryRouter()] },
  })
  expect(view.find('[data-milestone]').exists()).toBe(false)
  expect(view.get('h3').text()).toBe('Build the thing')
})

test('the_close_button_asks_to_close', async () => {
  const view = draw()
  await view.get('button[aria-label="Close"]').trigger('click')
  expect(view.emitted('close')).toHaveLength(1)
})

test('from_1024_px_the_peek_sits_beside_the_rows_and_is_no_dialog', () => {
  narrow(false)
  const view = draw()
  expect(view.get('aside').attributes('role')).toBeUndefined()
  expect(view.get('aside').attributes('aria-modal')).toBeUndefined()
  expect(document.activeElement).not.toBe(view.get('h3').element)
})

// An aside may not take the dialog role (ARIA in HTML): the sheet is a div.
test('below_1024_px_the_peek_is_a_modal_dialog_named_by_the_title_and_focus_moves_to_it', () => {
  narrow(true)
  const view = draw()
  const sheet = view.get('[role="dialog"]')
  expect([sheet.element.tagName, sheet.attributes('aria-modal')]).toEqual(['DIV', 'true'])
  expect(view.find('aside').exists()).toBe(false)
  expect(sheet.attributes('aria-labelledby')).toBe(view.get('h3').attributes('id'))
  expect(document.activeElement).toBe(view.get('h3').element)
})
