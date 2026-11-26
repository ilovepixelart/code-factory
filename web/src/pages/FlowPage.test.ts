// @vitest-environment happy-dom
// CF-1203: the Flow page shows what shipped and what is stuck in the window its address names,
// from the board's answer; the window is a link, and a read that fails keeps what was shown.
// CF-1215: beside what shipped, how much of it did not hold, each figure a link to its merges.

import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, test, vi } from 'vitest'
import type { Flow, Merged } from '../lib/metrics'
import { answer, memoryRouter, stubFetch } from '../test/board'
import { present } from '../test/present'
import { dashboard } from '../test/factory'
import FlowPage from './FlowPage.vue'

const GOLDEN = JSON.parse(
  readFileSync(
    join(import.meta.dirname, '../../../tests/golden/formats/metrics/flow.golden.json'),
    'utf8',
  ),
) as { query: string; flow: Flow }[]

/** The golden answer to `/api/flow?<query>`. */
function flowFor(query: string): Flow {
  const found = GOLDEN.find((entry) => entry.query === query)
  if (!found) throw new Error(`no golden flow for ${query}`)
  return structuredClone(found.flow)
}

const flowRouter = () =>
  memoryRouter([
    { path: '/analytics', component: FlowPage },
    { path: '/:rest(.*)*', component: { render: () => null } },
  ])

async function pageAt(
  address: string,
  change: (flow: Flow) => void = () => undefined,
  extra: (url: string) => Response | Promise<Response> | undefined = () => undefined,
) {
  document.body.innerHTML = '<div id="header-controls"></div><div id="app"></div>'
  const sent = stubFetch((url) => {
    const override = extra(url)
    if (override) return override
    if (url.startsWith('/api/factory/dashboard')) return answer(dashboard())
    const query = url.split('?')[1] ?? ''
    const flow = flowFor(query === 'range=7d' ? '' : query)
    change(flow)
    return answer(flow)
  })
  const router = flowRouter()
  await router.push(address)
  const page = mount(FlowPage, { attachTo: '#app', global: { plugins: [router] } })
  await flushPromises()
  return { page, router, sent }
}

const tile = (name: string) =>
  document.querySelector(`[aria-label="${name}"] [data-slot="card-title"]`)?.textContent.trim()
const tileNote = (name: string) =>
  document
    .querySelector(`[aria-label="${name}"] [data-slot="card-footer"]`)
    ?.textContent.replace(/\s+/g, ' ')
    .trim()
const rows = (heading: string) =>
  [
    ...(document.getElementById(heading)?.closest('section')?.querySelectorAll('tbody tr') ?? []),
  ].map((row) =>
    [...row.querySelectorAll('td')].map((cell) => cell.textContent.replace(/\s+/g, ' ').trim()),
  )
const windows = () =>
  [...document.querySelectorAll('nav[aria-label="Range"] a')].map((a) => ({
    text: a.textContent.trim(),
    href: a.getAttribute('href'),
    current: a.getAttribute('aria-current'),
  }))

/** Four merges, newest first: #4 held, #3 was reverted, #2 needed the fix CF-9 and no checks record
 *  names its head, #1 merged with its checks failed. */
function fourMerges(flow: Flow): void {
  const base = flow.merged[0]
  if (!base) throw new Error('the golden flow holds no merge')
  const row = (pull: number, change: Partial<Merged>): Merged => ({
    ...base,
    pull,
    ticket: `CF-${String(pull)}`,
    title: `Work ${String(pull)}`,
    reverted: false,
    fixes: [],
    checks: 'passed',
    ...change,
  })
  flow.merged = [
    row(4, {}),
    row(3, { reverted: true }),
    row(2, { fixes: ['CF-9'], checks: 'none' }),
    row(1, { checks: 'failed' }),
  ]
}
const heldLink = (name: string) =>
  document.querySelector(`[aria-label="${name}"] a`)?.getAttribute('href') ?? null
const mergedSection = () => document.getElementById('merged-heading')?.closest('section')

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

describe('the flow page', () => {
  test.each(['data', 'empty', 'error'] as const)(
    'the gate and question panels show their %s responses on demand',
    async (state) => {
      let release!: () => void
      const wait = new Promise<void>((resolve) => (release = resolve))
      const timing = { step: 'pytest', runs: 1, median: 200, slowest: 200, budget: 130 }
      const { page, sent } = await pageAt('/analytics', undefined, (url) => {
        const gate = url.startsWith('/api/gate-timings')
        if (!gate && !url.startsWith('/api/question-wait')) return undefined
        return wait.then(() => {
          if (state === 'error') return answer({ detail: 'Metrics unavailable' }, 503)
          if (gate) {
            return answer(
              state === 'empty' ? [] : [timing, { ...timing, step: 'build', budget: null }],
            )
          }
          return answer(
            state === 'empty'
              ? { answered: 0, median_seconds: null }
              : { answered: 2, median_seconds: 300 },
          )
        })
      })
      const gate = page.get('[aria-labelledby="gate-timings-heading"]')
      const question = page.get('[aria-labelledby="question-wait-heading"]')
      expect(sent.map(({ url }) => url)).not.toContain('/api/gate-timings')

      await gate.get('button').trigger('click')
      await question.get('button').trigger('click')

      expect(gate.text()).toContain('Reading gate timings')
      expect(question.text()).toContain('Reading response times')
      release()
      const expected = {
        data: ['Over budget', 'Median first response took 5m across 2 answered questions'],
        empty: ['No recorded gate timings', 'No first answers in this range'],
        error: ['Metrics unavailable', 'Metrics unavailable'],
      }[state]
      await vi.waitFor(() => {
        expect(gate.text()).toContain(expected[0])
        expect(question.text()).toContain(expected[1])
      })
    },
  )

  test('the_tiles_say_what_shipped_and_how_long_it_took_and_leave_cost_and_runs_to_factory', async () => {
    await pageAt('/analytics')

    expect(tile('Shipped')).toBe('1')
    expect(tile('Lead time')).toBe('3m')
    expect(tileNote('Lead time')).toBe('95% within 3m · 1 measured')
    expect(tile('Builds merged')).toBe('No data')
    expect(tile('In flight')).toBe('0')
    expect(tileNote('In flight')).toBe('none on a branch over 1d')
    expect(tile('Agent runs')).toBeUndefined()
    expect(tile('Cost per ticket')).toBeUndefined()
  })

  test('a_lead_time_tile_without_a_filed_ticket_names_the_merges_timed_from_a_first_commit', async () => {
    await pageAt('/analytics', (flow) => {
      fourMerges(flow)
      flow.merged.forEach((m, n) => (m.from = n < 3 ? 'first_commit' : 'filed'))
      flow.lead = { median: null, p85: null, p95: null, count: 0 }
    })

    expect(tile('Lead time')).toBe('No data')
    expect(tileNote('Lead time')).toBe('no filed ticket to time from; 3 timed from a first commit')
  })

  test('a_lead_time_tile_with_no_merge_says_no_lead_time_was_measured', async () => {
    await pageAt('/analytics', (flow) => {
      flow.merged = []
      flow.lead = { median: null, p85: null, p95: null, count: 0 }
    })

    expect(tileNote('Lead time')).toBe('no measured lead times')
  })

  test('the_tiles_show_the_median_minutes_per_column', async () => {
    await pageAt('/analytics', (flow) => {
      flow.columns = { spec: 10, build: 90, review: null }
    })

    expect(tile('Spec time')).toBe('10m')
    expect(tile('Build time')).toBe('1.5h')
    expect(tile('Review time')).toBe('No data')
  })

  test('a_column_left_within_a_minute_reads_under_a_minute_not_zero', async () => {
    await pageAt('/analytics', (flow) => {
      flow.columns = { spec: 0, build: 0.4, review: 1 }
    })

    expect([tile('Spec time'), tile('Build time'), tile('Review time')]).toEqual([
      'under 1m',
      'under 1m',
      '1m',
    ])
  })

  test('a_tile_with_no_figure_shows_a_muted_placeholder', async () => {
    await pageAt('/analytics', (flow) => {
      flow.columns = { spec: 10, build: 90, review: null }
    })

    const figure = document.querySelector('[aria-label="Review time"] [data-slot="card-title"]')
    expect(figure?.classList.contains('text-muted-foreground')).toBe(true)
    expect(
      document
        .querySelector('[aria-label="Spec time"] [data-slot="card-title"]')
        ?.classList.contains('text-muted-foreground'),
    ).toBe(false)
  })

  // Outcomes lead (docs/ui.md, Flow): what a person's attention was spent on, stated as its cost.
  test('human_intervention_is_the_share_of_classed_merges_that_needed_a_hand_commit', async () => {
    await pageAt('/analytics', (flow) => {
      flow.autonomy = { share: 2 / 3, autonomous: 2, assisted: 1, unknown: 4 }
    })

    expect([tile('Human intervention'), tileNote('Human intervention')]).toEqual([
      '33%',
      '1 of 3 merges needed a hand commit, 4 unknown',
    ])
  })

  test('a_range_with_no_classed_merge_shows_no_intervention_figure', async () => {
    await pageAt('/analytics', (flow) => {
      flow.autonomy = { share: null, autonomous: 0, assisted: 0, unknown: 1 }
    })

    expect([tile('Human intervention'), tileNote('Human intervention')]).toEqual([
      'No data',
      '0 of 0 merges needed a hand commit, 1 unknown',
    ])
  })

  // First-pass yield: of the range's merges, those that held, neither reverted nor fixed by a later
  // ticket. Four merges, one reverted and one fixed: two held, 50%.
  test('first_pass_yield_is_the_share_of_merges_neither_reverted_nor_fixed', async () => {
    await pageAt('/analytics', (flow) => {
      const one = present(flow.merged[0], 'a merged row')
      flow.merged = [
        { ...one, title: 'a', reverted: false, fixes: [] },
        { ...one, title: 'b', reverted: true, fixes: [] },
        { ...one, title: 'c', reverted: false, fixes: ['CF-9'] },
        { ...one, title: 'd', reverted: false, fixes: [] },
      ]
    })

    expect([tile('First-pass yield'), tileNote('First-pass yield')]).toEqual([
      '50%',
      '2 of 4 merges held: not reverted, no later fix',
    ])
  })

  test('a_range_without_a_merge_has_no_yield', async () => {
    await pageAt('/analytics', (flow) => {
      flow.merged = []
    })

    expect([tile('First-pass yield'), tileNote('First-pass yield')]).toEqual([
      'No data',
      'no merge in this range',
    ])
  })

  // The page reads outcomes first: yield and intervention, then whether shipped work held, then
  // throughput.
  test('outcomes_come_before_what_held_and_before_throughput', async () => {
    await pageAt('/analytics')
    const order = [...document.querySelectorAll('[aria-label]')]
      .map((e) => e.getAttribute('aria-label') ?? '')
      .filter((label) =>
        ['First-pass yield', 'Human intervention', 'Reverted', 'Shipped'].includes(label),
      )

    expect(order).toEqual(['First-pass yield', 'Human intervention', 'Reverted', 'Shipped'])
  })

  test('the_range_sits_in_the_toolbar_and_the_header_holds_only_the_tab_switch', async () => {
    await pageAt('/analytics')

    expect(
      document.querySelector('[data-analytics-toolbar] nav[aria-label="Range"]'),
    ).not.toBeNull()
    expect(
      [...document.querySelectorAll('#header-controls nav')].map((n) =>
        n.getAttribute('aria-label'),
      ),
    ).toEqual(['Analytics pages'])
  })

  test('the_range_is_a_link_and_the_current_one_is_marked', async () => {
    const { sent, router } = await pageAt('/analytics')

    expect(windows()).toEqual([
      { text: '24 hours', href: '/analytics?range=24h', current: null },
      { text: '7 days', href: '/analytics', current: 'page' },
      { text: '30 days', href: '/analytics?range=30d', current: null },
      { text: '90 days', href: '/analytics?range=90d', current: null },
    ])
    await router.push('/analytics?range=30d')
    await flushPromises()
    expect(sent.filter((s) => s.url.startsWith('/api/flow')).at(-1)?.url).toBe(
      '/api/flow?range=30d',
    )
  })

  test('recently_merged_lists_each_pull_request_with_its_ticket_and_lead', async () => {
    await pageAt('/analytics')

    expect(rows('merged-heading')).toEqual([
      ['CF-50 Idea 50', '#7', '3m', 'unchecked', expect.stringMatching(/ago$/)],
    ])
  })

  // Every row of Stuck is past the threshold, so red on all of them says nothing: an age is red
  // only past twice the threshold.
  test('a_stuck_age_is_red_only_past_twice_the_threshold', async () => {
    await pageAt('/analytics', (flow) => {
      flow.in_flight = 2
      flow.stuck_after = 86_400
      const stuck = (id: string, age: number) => ({
        repository: 'sample',
        id,
        title: 'Long work',
        stage: 'build' as const,
        age,
        needs: '',
      })
      flow.stuck = [stuck('CF-1', 2 * 86_400), stuck('CF-2', 3 * 86_400)]
    })
    const section = document.querySelector('#stuck-heading')?.closest('section')

    expect(rows('stuck-heading')).toEqual([
      ['CF-1 Long work', 'Build', '2d'],
      ['CF-2 Long work', 'Build', '3d'],
    ])
    expect(
      [...(section?.querySelectorAll('.text-destructive') ?? [])].map((e) => e.textContent),
    ).toEqual(['3d'])
    expect(tileNote('In flight')).toBe('2 on a branch over 1d')
  })

  test('both_flow_tables_name_their_columns_with_the_terms_every_table_uses', async () => {
    await pageAt('/analytics', (flow) => {
      fourMerges(flow)
      flow.stuck = [
        { repository: 'sample', id: 'CF-1', title: 'Long work', stage: 'build', age: 1, needs: '' },
      ]
    })
    const heads = (heading: string) =>
      [...(document.getElementById(heading)?.closest('section')?.querySelectorAll('th') ?? [])].map(
        (th) => th.textContent.trim(),
      )

    expect(heads('stuck-heading')).toEqual(['Ticket', 'Stage', 'On its branch'])
    expect(heads('merged-heading').slice(0, 3)).toEqual(['Ticket', 'Pull request', 'Lead'])
  })

  test('a_filtered_section_counts_what_its_filter_keeps_of_all', async () => {
    await pageAt('/analytics?merged_q=Work%201', (flow) => {
      fourMerges(flow)
      flow.stuck = [
        { repository: 'sample', id: 'CF-7', title: 'Long work', stage: 'build', age: 1, needs: '' },
      ]
    })
    const count = document.querySelector('#merged-heading .tabular-nums')?.textContent.trim()

    expect(count).toBe('1 of 4')
    expect(
      document
        .getElementById('stuck-heading')
        ?.closest('section')
        ?.querySelector('input[type="search"]')
        ?.getAttribute('aria-label') ?? 'none',
    ).not.toBe('none')
  })

  test('the_needs_column_shows_only_while_a_stuck_ticket_records_a_need', async () => {
    await pageAt('/analytics', (flow) => {
      flow.in_flight = 2
      flow.stuck = [
        {
          repository: 'sample',
          id: 'CF-1',
          title: 'Long work',
          stage: 'build',
          age: 2 * 86_400,
          needs: 'a review',
        },
        {
          repository: 'sample',
          id: 'CF-2',
          title: 'Other',
          stage: 'build',
          age: 86_400 * 3,
          needs: '',
        },
      ]
    })

    expect(rows('stuck-heading')).toContainEqual(['CF-1 Long work', 'Build', '2d', 'a review'])
    expect(rows('stuck-heading')).toContainEqual(['CF-2 Other', 'Build', '3d', ''])
  })

  test('the_stuck_description_says_what_stuck_means_in_plain_words', async () => {
    await pageAt('/analytics')

    expect(
      document
        .getElementById('stuck-heading')
        ?.closest('section')
        ?.querySelector('[data-slot="section-description"]')
        ?.textContent.trim(),
    ).toBe(
      'On a branch longer than 1d: the time 85% of merged tickets took, or a day until 5 merges set it',
    )
  })

  test('nothing_stuck_says_so_in_one_line', async () => {
    await pageAt('/analytics')

    expect(document.getElementById('stuck-heading')?.closest('section')?.textContent).toContain(
      'Nothing on a branch longer than 1d',
    )
  })

  test('a_refused_read_keeps_what_the_page_showed', async () => {
    document.body.innerHTML = '<div id="header-controls"></div><div id="app"></div>'
    stubFetch((url) =>
      url === '/api/flow?range=7d'
        ? answer(flowFor(''))
        : answer({ detail: 'no such window' }, 400),
    )
    const router = flowRouter()
    await router.push('/analytics')
    mount(FlowPage, { attachTo: '#app', global: { plugins: [router] } })
    await flushPromises()

    await router.push('/analytics?range=24h')
    await flushPromises()

    expect(tile('Shipped')).toBe('1')
  })

  test('the_held_tiles_count_what_did_not_hold_and_its_share', async () => {
    await pageAt('/analytics', fourMerges)

    expect(tile('Reverted')).toBe('1')
    expect(tileNote('Reverted')).toBe('25% of 4 merged · show them')
    expect(tile('Needed a fix')).toBe('1')
    expect(tileNote('Needed a fix')).toBe('25% of 4 merged · show them')
    expect(tile('Unchecked')).toBe('2')
    expect(tileNote('Unchecked')).toBe('50% of 4 merged · show them')
  })

  test('a_held_figure_links_to_its_merges_and_one_of_none_links_nowhere', async () => {
    await pageAt('/analytics?range=30d', (flow) => {
      fourMerges(flow)
      flow.merged = flow.merged.filter((m) => !m.reverted)
    })

    expect(tile('Reverted')).toBe('0')
    expect(tileNote('Reverted')).toBe('0% of 3 merged')
    expect(heldLink('Reverted')).toBeNull()
    expect(heldLink('Needed a fix')).toBe('/analytics?range=30d&held=fixed')
    expect(heldLink('Unchecked')).toBe('/analytics?range=30d&held=unchecked')
  })

  test('a_range_with_no_merge_has_no_share', async () => {
    await pageAt('/analytics', (flow) => {
      flow.merged = []
    })

    expect(tile('Unchecked')).toBe('0')
    expect(tileNote('Unchecked')).toBe('no merge in this range')
  })

  test('the_merged_list_sorts_by_the_column_its_address_names_and_stops_saying_newest_first', async () => {
    const note = () =>
      mergedSection()?.querySelector('[data-slot="section-description"]')?.textContent.trim()
    const leads = (flow: Flow) => {
      fourMerges(flow)
      flow.merged.forEach((m, n) => (m.lead = [600, 60, 3600, 120][n] ?? 0))
    }
    await pageAt('/analytics', leads)
    expect(rows('merged-heading').map((cells) => cells[0])).toEqual([
      'CF-4 Work 4',
      'CF-3 Work 3',
      'CF-2 Work 2',
      'CF-1 Work 1',
    ])
    expect(note()).toBe('newest first; lead is from filing the ticket to the merge')

    await pageAt('/analytics?merged_sort=lead&merged_dir=asc', leads)
    expect(rows('merged-heading').map((cells) => cells[0])).toEqual([
      'CF-3 Work 3',
      'CF-1 Work 1',
      'CF-4 Work 4',
      'CF-2 Work 2',
    ])
    expect(note()).toBe('lead is from filing the ticket to the merge')
  })

  test('the_filter_in_the_address_lists_only_those_merges', async () => {
    await pageAt('/analytics?held=unchecked', fourMerges)

    expect(rows('merged-heading')).toEqual([
      ['CF-2 Work 2', '#2', '3m', 'fixed by CF-9 unchecked', expect.stringMatching(/ago$/)],
      ['CF-1 Work 1', '#1', '3m', 'checks failed', expect.stringMatching(/ago$/)],
    ])
    const all = mergedSection()?.querySelector('[data-slot="section-action"] a')
    expect(all?.textContent.trim()).toBe('all 4 merged')
    expect(all?.getAttribute('href')).toBe('/analytics')
  })

  test('a_merge_row_says_how_it_held_and_links_its_fix', async () => {
    await pageAt('/analytics', fourMerges)

    expect(rows('merged-heading').map((cells) => cells[3])).toEqual([
      'checks passed',
      'reverted checks passed',
      'fixed by CF-9 unchecked',
      'checks failed',
    ])
    expect(
      mergedSection()
        ?.querySelector('tbody tr:nth-child(3) td:nth-child(4) a')
        ?.getAttribute('href'),
    ).toBe('/tickets/sample/CF-9')
    expect(mergedSection()?.querySelector('[data-slot="section-action"] a')).toBeNull()
  })

  test('a_filter_with_no_merge_says_so', async () => {
    await pageAt('/analytics?held=reverted')

    expect(mergedSection()?.textContent).toContain('No merge in this range was reverted')
  })

  test('an_unknown_filter_lists_every_merge', async () => {
    await pageAt('/analytics?held=everything', fourMerges)

    expect(rows('merged-heading')).toHaveLength(4)
  })
})
