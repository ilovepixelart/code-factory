// The Factory page reads the dashboard of the range its address names and draws it: what a cohort
// of work cost and how it went. Every expected value is worked by hand from the specification's
// fixture F1 (section 4.4), never taken from what the page drew.

import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { shownTab } from '@/lib/analytics'
import { ESTIMATE_NOTE } from '@/lib/format'
import { dashboard, emptyDashboard, improvements } from '../../support/factory'
import { present } from '../../support/present'
import {
  json,
  links,
  pageAt,
  readAgain,
  rows,
  section,
  tile,
  tileNote,
  tileText,
  words,
} from '../../support/factoryPage'
import FactoryPage from '@/pages/FactoryPage.vue'

/** A scorer's lines in order: its title, its descriptions, the lines of its body, its rate. */
const LINES = '[data-slot="item-title"], [data-slot="item-description"], p'

const served =
  (change: (d: ReturnType<typeof dashboard>) => void = () => undefined) =>
  () => {
    const answer = dashboard()
    change(answer)
    return json(answer)
  }
const show = (address = '/analytics/factory', change?: Parameters<typeof served>[0]) =>
  pageAt(FactoryPage, address, served(change))

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

describe('the read', () => {
  test('the_default_range_reads_the_last_7_days_with_today_inside', async () => {
    const { sent } = await show()

    expect(sent.map((s) => s.url)).toEqual(['/api/factory/dashboard?from=2026-11-04&to=2026-11-11'])
  })

  test('the_address_names_a_longer_range_and_24_hours_reads_today', async () => {
    const { sent } = await show('/analytics/factory?range=30d')
    const day = await show('/analytics/factory?range=24h')

    expect(sent.at(-1)?.url).toBe('/api/factory/dashboard?from=2026-10-12&to=2026-11-11')
    expect(day.sent.at(-1)?.url).toBe('/api/factory/dashboard?from=2026-11-10&to=2026-11-11')
  })

  test('the_range_and_the_pages_are_links_and_the_current_ones_are_marked', async () => {
    await show('/analytics/factory?range=90d')

    expect(links('Range')).toEqual([
      { text: '24 hours', href: '/analytics/factory?range=24h', current: null },
      { text: '7 days', href: '/analytics/factory', current: null },
      { text: '30 days', href: '/analytics/factory?range=30d', current: null },
      { text: '90 days', href: '/analytics/factory?range=90d', current: 'page' },
    ])
    expect(links('Analytics pages')).toEqual([
      { text: 'Flow', href: '/analytics?range=90d', current: null },
      { text: 'Factory', href: '/analytics/factory?range=90d', current: 'page' },
      { text: 'Scorers', href: '/analytics/scorers?range=90d', current: null },
    ])
  })

  test('the_toolbar_says_the_numbers_are_estimates_to_pick_runs_from', async () => {
    await show()

    expect(document.querySelector('[data-analytics-toolbar]')?.textContent).toContain(
      'Estimates, not an invoice. Use these to pick runs to investigate, not to conclude a cause.',
    )
  })
})

describe('the tiles', () => {
  test('analytics shows fix-round outcomes and role notes linked to fixed findings', async () => {
    await show('/analytics/factory?role_notes_sort=share&role_notes_dir=desc', (dashboard) => {
      dashboard.fix_rounds = [
        { rounds: 1, merged: 2, closed: 1, open: 1, merge_rate: 2 / 3 },
        { rounds: 2, merged: 0, closed: 0, open: 1, merge_rate: null },
      ]
      dashboard.role_notes = [
        { role: 'qa', notes: 4, fixed: 1 },
        { role: 'tests', notes: 2, fixed: 1 },
      ]
    })

    const text = (id: string): string =>
      document.getElementById(id)?.closest('section')?.textContent ?? ''
    expect(text('fix-rounds-heading')).toContain('66.7%')
    expect(text('fix-rounds-heading')).toContain('Closed unmerged')
    expect(text('role-notes-heading')).toContain('25%')
    expect(rows('role-notes-heading').map((row) => row[0])).toEqual(['tests', 'qa'])
  })

  test('the_tiles_read_the_fixtures_counts_spans_and_costs', async () => {
    await show()

    expect(tileText('Runs')).toBe('13')
    expect(tileNote('Runs')).toBe('9 finished, 2 failed, 1 stopped')
    expect(tileText('PRs opened')).toBe('7')
    expect(tileNote('PRs opened')).toBe('2 open, 1 closed unmerged')
    // Merges, cycle time and autonomy are the Flow page's.
    expect([
      tile('PRs merged'),
      tile('PR cycle time'),
      tile('Built without a hand commit'),
    ]).toEqual([null, null, null])
    expect(tileText('Cost per PR')).toBe('$1.75')
    expect(tileNote('Cost per PR')).toBe('median; 6 of 7 PRs priced')
    expect(tileText('Measurement spend')).toBe('$0.50')
    expect(tileNote('Measurement spend')).toBe('judges and evals, not in PR cost')
  })

  test('an_estimated_cost_is_led_by_a_tilde', async () => {
    await show('/analytics/factory', (d) => {
      d.cost.estimated = true
    })

    expect(tileText('Cost per PR')).toBe('~$1.75')
    expect(
      document
        .querySelector('[aria-label="Cost per PR"] [data-slot="card-footer"] p')
        ?.getAttribute('title'),
    ).toBe(ESTIMATE_NOTE)
  })

  test('a_measured_cost_has_no_estimate_note', async () => {
    await show()

    expect(
      document
        .querySelector('[aria-label="Cost per PR"] [data-slot="card-footer"] p')
        ?.hasAttribute('title'),
    ).toBe(false)
  })

  test('a_range_with_no_data_reads_zero_counts_none_for_medians_and_says_why', async () => {
    await pageAt(FactoryPage, '/analytics/factory', () => json(emptyDashboard()))

    expect(tileText('Runs')).toBe('0')
    expect(tileText('PRs opened')).toBe('0')
    expect(tileText('Cost per PR')).toBe('No data')
    expect(tileNote('Cost per PR')).toBe('no pull requests opened in this range')
    expect(tileText('Measurement spend')).toBe('$0.00')
  })
})

describe('cost per pull request', () => {
  test('the_component_table_reads_the_fixtures_medians_and_totals', async () => {
    await show()

    expect(rows('cost-heading').slice(0, 4)).toEqual([
      ['Spec', '$0.00', '$0.50'],
      ['Build', '$1.50', '$16.00'],
      ['Review', '$0.50', '$5.00'],
      ['Other', '$0.00', '$0.00'],
    ])
  })

  test('the_size_table_reads_the_fixtures_medians_and_how_many_were_priced', async () => {
    await show()

    expect(rows('cost-heading').slice(4)).toEqual([
      ['S, under 100 lines', '$1.50', '2 of 2'],
      ['M, 100 to 499 lines', '$3.50', '2 of 2'],
      ['L, 500 to 999 lines', '$1.50', '1 of 2'],
      ['XL, 1000 lines and up', '$10.00', '1 of 1'],
    ])
  })

  // A missing figure reads as the tiles' muted "No data", not a word in the figure's place.
  test('a_size_with_nothing_priced_reads_no_data_muted', async () => {
    await show('/analytics/factory', (d) => {
      d.cost.by_size[2] = { size: 'L', median: 0, priced: 0, of: 2 }
    })
    const cell = section('cost-heading')?.querySelectorAll('tbody tr')[6]?.querySelectorAll('td')[1]

    expect(rows('cost-heading')[6]).toEqual(['L, 500 to 999 lines', 'No data', '0 of 2'])
    expect(cell?.querySelector('span')?.className).toContain('text-muted-foreground')
  })

  test('pull_requests_without_a_cost_are_counted_in_a_muted_line', async () => {
    await show()

    expect(words(section('cost-heading')?.querySelector('[data-unpriced]'))).toBe(
      '1 PR has no recorded cost',
    )
  })

  test('several_unpriced_pull_requests_are_counted_in_the_plural', async () => {
    await show('/analytics/factory', (d) => {
      d.cost.priced = 4
    })

    expect(words(section('cost-heading')?.querySelector('[data-unpriced]'))).toBe(
      '3 PRs have no recorded cost',
    )
  })

  test('when_every_pull_request_is_priced_there_is_no_such_line', async () => {
    await show('/analytics/factory', (d) => {
      d.cost.priced = 7
    })

    expect(section('cost-heading')?.querySelector('[data-unpriced]')).toBeNull()
  })

  test('no_priced_pull_request_says_none_has_a_recorded_cost', async () => {
    await pageAt(FactoryPage, '/analytics/factory', () => json(emptyDashboard()))

    expect(section('cost-heading')?.querySelector('table')).toBeNull()
    expect(words(section('cost-heading'))).toContain('No pull request has a recorded cost')
  })
})

describe('runs', () => {
  const tabs = () =>
    [...document.querySelectorAll('[role="tablist"][aria-label="Group runs by"] [role="tab"]')].map(
      (t) => ({ text: words(t), selected: t.getAttribute('aria-selected') }),
    )

  test('runs_are_grouped_by_stage_with_each_ones_share_of_the_13', async () => {
    await show()

    expect(tabs().map((t) => t.text)).toEqual(['Stage', 'State', 'Source', 'Model', 'Agent'])
    expect(tabs()[0]?.selected).toBe('true')
    // 6, 4, 1, 1, 1 of 13: 46.2, 30.8, 7.7 each.
    expect(rows('runs-heading')).toEqual([
      ['build', '6', '46%'],
      ['review', '4', '31%'],
      ['eval', '1', '8%'],
      ['judge', '1', '8%'],
      ['spec', '1', '8%'],
    ])
    expect(section('runs-heading')?.textContent).toContain(
      'includes judge, eval and benchmark runs; more runs with the same PRs can mean retries or measurement',
    )
  })

  test('choosing_another_grouping_shows_its_rows', async () => {
    await show()

    const model = [...document.querySelectorAll('[role="tab"]')].find(
      (t) => words(t) === 'Model',
    ) as HTMLElement
    // A tab is chosen as the mouse button goes down.
    model.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, button: 0 }))
    await flushPromises()

    // 8 and 5 of 13: 61.5 and 38.5.
    expect(rows('runs-heading')).toEqual([
      ['opus', '8', '62%'],
      ['sonnet', '5', '38%'],
    ])
    expect(tabs().map((t) => t.selected)).toEqual(['false', 'false', 'false', 'true', 'false'])
  })

  test('a_key_the_server_leaves_empty_reads_unknown', async () => {
    await show('/analytics/factory', (d) => {
      d.runs.by_stage = [{ key: '', runs: 13 }]
    })

    expect(rows('runs-heading')).toEqual([['unknown', '13', '100%']])
  })

  test('no_runs_says_so_instead_of_a_table', async () => {
    await pageAt(FactoryPage, '/analytics/factory', () => json(emptyDashboard()))

    expect(section('runs-heading')?.querySelector('table')).toBeNull()
    expect(words(section('runs-heading'))).toContain('No runs in this range')
  })
})

describe('the most expensive pull requests', () => {
  test('the_fixtures_five_are_listed_dearest_first_with_their_ticket_size_runs_cost_and_state', async () => {
    await show()

    expect(rows('expensive-heading')).toEqual([
      ['#14 Cache the index', 'CF-4', 'XL', '2', '$10.00', 'Open'],
      ['#12 Split the loader', 'CF-2', 'M', '3', '$5.00', 'Merged'],
      ['#13 Retry the fetch', 'CF-3', 'M', '1', '$2.00', 'Merged'],
      ['#17 Trim the log', 'CF-6', 'S', '2', '$1.50', 'Merged'],
      ['#16 Warm the cache', 'CF-6', 'L', '2', '$1.50', 'Open'],
    ])
  })

  test('the_number_links_to_the_pull_request_and_the_ticket_to_the_board', async () => {
    await show()

    const first = section('expensive-heading')?.querySelector('tbody tr')
    expect(first?.querySelector('a[href^="https://"]')?.getAttribute('href')).toBe(
      'https://github.com/sample/sample/pull/14',
    )
    expect(first?.querySelector('a[href^="https://"]')?.getAttribute('rel')).toBe(
      'noopener noreferrer',
    )
    expect(first?.querySelector('a[href^="/tickets"]')?.getAttribute('href')).toBe(
      '/tickets/sample/CF-4',
    )
  })

  test('only_the_top_five_are_shown', async () => {
    await show('/analytics/factory', (d) => {
      const [first] = d.expensive
      if (first) d.expensive.push({ ...first, number: 99 })
    })

    expect(rows('expensive-heading')).toHaveLength(5)
  })

  // A fixed top five needs no paging; it says what it holds and names its columns with the terms
  // every table uses, its amounts right-aligned like every other table's.
  test('the_top_five_says_so_and_its_amounts_line_up_on_the_right', async () => {
    await show()
    const heads = [...(section('expensive-heading')?.querySelectorAll('th') ?? [])]
    const runHeads = [...(section('runs-heading')?.querySelectorAll('th') ?? [])]

    expect(section('expensive-heading')?.textContent).toContain('The five dearest pull requests')
    expect(heads.map((th) => th.textContent.trim())).toEqual([
      'Pull request',
      'Ticket',
      'Size',
      'Runs',
      'Cost',
      'State',
    ])
    expect(
      [...heads.slice(3, 5), ...runHeads.slice(1)].map((th) => th.classList.contains('text-right')),
    ).toEqual([true, true, true, true])
    expect(
      section('runs-heading')
        ?.querySelector('tbody td:nth-child(2)')
        ?.classList.contains('font-medium'),
    ).toBe(true)
  })

  test('the_repository_is_named_only_when_the_list_spans_more_than_one', async () => {
    await show()
    expect(rows('expensive-heading')[0]?.[0]).toBe('#14 Cache the index')

    await show('/analytics/factory', (d) => {
      const [first] = d.expensive
      if (first) first.repository = 'other'
    })
    expect(rows('expensive-heading')[0]?.[0]).toBe('#14 Cache the index other')
    expect(rows('expensive-heading')[1]?.[0]).toBe('#12 Split the loader sample')
  })

  test('a_cost_missing_a_run_is_marked_partial', async () => {
    await show('/analytics/factory', (d) => {
      const [first] = d.expensive
      if (first) first.cost_complete = false
    })

    expect(rows('expensive-heading')[0]?.[4]).toBe('$10.00 Partial')
    expect(rows('expensive-heading')[1]?.[4]).toBe('$5.00')
  })

  test('an_estimated_cost_is_led_by_a_tilde', async () => {
    await show('/analytics/factory', (d) => {
      const [first] = d.expensive
      if (first) first.estimated = true
    })

    expect(rows('expensive-heading')[0]?.[4]).toBe('~$10.00')
    const cells = [
      ...(section('expensive-heading')?.querySelectorAll('tbody tr td:nth-child(5)') ?? []),
    ]
    expect(cells.map((c) => c.getAttribute('title'))).toEqual([
      ESTIMATE_NOTE,
      null,
      null,
      null,
      null,
    ])
  })

  test('estimated_component_and_size_costs_carry_the_note', async () => {
    await show('/analytics/factory', (d) => {
      d.cost.estimated = true
    })

    const cells = [
      ...(section('cost-heading')?.querySelectorAll('tbody td.tabular-nums[title]') ?? []),
    ]
    expect(cells.length).toBeGreaterThan(0)
    expect(new Set(cells.map((c) => c.getAttribute('title')))).toEqual(new Set([ESTIMATE_NOTE]))
  })

  test('a_pull_request_with_no_ticket_and_no_recorded_size_says_so', async () => {
    await show('/analytics/factory', (d) => {
      const [first] = d.expensive
      if (first) Object.assign(first, { ticket: null, size: 'unknown', changed_lines: null })
    })

    expect(rows('expensive-heading')[0]).toEqual([
      '#14 Cache the index',
      'none',
      'unknown',
      '2',
      '$10.00',
      'Open',
    ])
  })

  test('no_priced_pull_request_says_so', async () => {
    await pageAt(FactoryPage, '/analytics/factory', () => json(emptyDashboard()))

    expect(words(section('expensive-heading'))).toContain('No priced pull requests')
    expect(section('expensive-heading')?.querySelector('table')).toBeNull()
  })
})

describe('scorers', () => {
  const cards = () => [...(section('scorers-heading')?.querySelectorAll('[data-scorer]') ?? [])]

  test('a_card_names_the_scorer_its_question_pass_rate_answers_and_window', async () => {
    await show()

    expect([...(cards()[0]?.querySelectorAll(LINES) ?? [])].map((p) => words(p))).toEqual([
      'ran-tests',
      'Did the agent run the tests before finishing?',
      '5 answers, last 7 days',
      '75%',
    ])
  })

  test('an_average_score_shows_when_the_scorer_has_one', async () => {
    await show('/analytics/factory', (d) => {
      const [card] = d.scorers.cards
      if (card) card.average_score = 2 / 3
    })

    expect(words(cards()[0]?.querySelector('[data-average]'))).toBe('average score 67%')
  })

  test('the_section_links_to_all_scorers', async () => {
    await show()

    expect(
      section('scorers-heading')?.querySelector('a[href="/analytics/scorers"]')?.textContent.trim(),
    ).toBe('All scorers')
  })

  test('the_link_to_all_scorers_keeps_the_range', async () => {
    await show('/analytics/factory?range=30d')

    expect(
      section('scorers-heading')
        ?.querySelector('a[href^="/analytics/scorers"]')
        ?.getAttribute('href'),
    ).toBe('/analytics/scorers?range=30d')
  })

  test('a_card_names_its_repository_only_when_the_scorers_span_several', async () => {
    await show()
    expect(document.querySelector('[data-repository]')).toBeNull()

    await show('/analytics/factory', (d) => {
      const [first] = d.scorers.cards
      if (first) d.scorers.cards.push({ ...first, repository: 'other' })
    })
    expect([...document.querySelectorAll('[data-repository]')].map((r) => words(r))).toEqual([
      'sample',
      'other',
    ])
  })

  test('no_scorer_defined_says_where_to_define_one', async () => {
    await show('/analytics/factory', (d) => {
      d.scorers = { available: true, cards: [] }
    })

    expect(cards()).toHaveLength(0)
    expect(words(section('scorers-heading'))).toContain(
      'No scorers definedAdd [[scorers]] to .code-factory/config.toml.',
    )
  })

  test('scorers_not_yet_available_is_an_empty_state_not_an_error', async () => {
    await show('/analytics/factory', (d) => {
      d.scorers = { available: false, cards: [] }
    })

    expect(words(section('scorers-heading'))).toContain('Scorer results are not available yet')
    expect(document.querySelector('[role="alert"]')).toBeNull()
  })
})

describe('newest self-improvement pull requests', () => {
  // Until the evals that feed it exist the page offers no section that can only say so.
  test('not_yet_available_shows_no_section_and_no_error', async () => {
    await show()

    expect(section('improvements-heading')).toBeNull()
    expect(document.querySelector('[role="alert"]')).toBeNull()
  })

  test('an_item_links_its_number_names_its_title_state_and_age', async () => {
    await show('/analytics/factory', (d) => {
      d.improvements = improvements()
    })

    // now Nov 10 00:00, opened Nov 6 21:20: 268800 s, 3.1 days.
    expect(
      [
        ...(section('improvements-heading')
          ?.querySelector('[data-slot="item"]')
          ?.querySelectorAll(
            '[data-slot="item-media"], [data-slot="item-title"], [data-slot="item-actions"] > *',
          ) ?? []),
      ].map(words),
    ).toEqual(['#21', 'Self-improvement: 25 failures', 'Open', '3.1d ago'])
    expect(
      section('improvements-heading')?.querySelector('[data-slot="item"] a')?.getAttribute('href'),
    ).toBe('https://github.com/sample/sample/pull/21')
    // The link to the whole list shows only while its tab does (HIDDEN_TABS).
    expect(
      section('improvements-heading')
        ?.querySelector('a[href="/analytics/self-improvement"]')
        ?.textContent.trim(),
    ).toBe(shownTab('/analytics/self-improvement') ? 'All self-improvement' : undefined)
  })

  test('available_with_none_says_there_are_none_yet', async () => {
    await show('/analytics/factory', (d) => {
      d.improvements = { available: true, items: [] }
    })

    expect(words(section('improvements-heading'))).toContain(
      'No self-improvement pull requests yet',
    )
  })
})

describe('the states of the page', () => {
  test('until_the_first_answer_the_page_says_it_is_reading_the_factory', async () => {
    await pageAt(FactoryPage, '/analytics/factory', () => new Promise<Response>(() => undefined))

    expect(document.body.textContent).toContain('Reading the factory')
    expect(document.querySelector('[aria-label="Runs"]')).toBeNull()
    expect(links('Analytics pages')).toHaveLength(3)
  })

  test('a_refused_read_shows_the_servers_sentence_and_reads_again_on_request', async () => {
    let refuse = true
    const { wrapper } = await pageAt(FactoryPage, '/analytics/factory', () =>
      refuse ? json({ detail: 'from must be before to' }, 400) : json(dashboard()),
    )

    expect(document.querySelector('[role="alert"]')?.textContent).toContain(
      'from must be before to',
    )
    refuse = false
    readAgain()
    await flushPromises()

    expect(tileText('Runs')).toBe('13')
    expect(document.querySelector('[role="alert"]')).toBeNull()
    wrapper.unmount()
  })

  test('a_range_change_keeps_the_old_figures_with_a_loading_line_until_the_new_answer', async () => {
    let release: (response: Response) => void = () => undefined
    let pending = false
    const { router } = await pageAt(FactoryPage, '/analytics/factory', () =>
      pending
        ? new Promise<Response>((resolve) => {
            release = resolve
          })
        : json(dashboard()),
    )
    expect(document.querySelector('[data-reading]')).toBeNull()

    pending = true
    await router.push('/analytics/factory?range=30d')
    await flushPromises()

    expect(tileText('Runs')).toBe('13')
    expect(words(document.querySelector('[data-reading]'))).toBe('Reading')
    const next = dashboard()
    next.runs.total = 5
    release(json(next))
    await flushPromises()

    expect(tileText('Runs')).toBe('5')
    expect(document.querySelector('[data-reading]')).toBeNull()
  })

  test('only_the_latest_read_applies_however_late_an_earlier_one_answers', async () => {
    const held: ((response: Response) => void)[] = []
    const { router } = await pageAt(
      FactoryPage,
      '/analytics/factory',
      () =>
        new Promise<Response>((resolve) => {
          held.push(resolve)
        }),
    )
    await router.push('/analytics/factory?range=30d')
    await flushPromises()
    const latest = dashboard()
    latest.runs.total = 7
    const stale = dashboard()
    stale.runs.total = 99

    held[1]?.(json(latest))
    await flushPromises()
    held[0]?.(json(stale))
    await flushPromises()

    expect(tileText('Runs')).toBe('7')
  })

  test('a_read_that_fails_after_data_keeps_the_figures_and_says_why_in_a_row', async () => {
    let refuse = false
    const { router } = await pageAt(FactoryPage, '/analytics/factory', () =>
      refuse ? json({ detail: 'the store is busy' }, 503) : json(dashboard()),
    )

    refuse = true
    await router.push('/analytics/factory?range=30d')
    await flushPromises()

    expect(tileText('Runs')).toBe('13')
    expect(words(document.querySelector('[data-factory-notice] [data-slot="alert-title"]'))).toBe(
      'the store is busy; still showing the last 7 days',
    )
  })

  test('the_row_offers_read_again_for_the_range_asked', async () => {
    let refuse = false
    const { router } = await pageAt(FactoryPage, '/analytics/factory', () =>
      refuse ? json({ detail: 'the store is busy' }, 503) : json(dashboard()),
    )
    refuse = true
    await router.push('/analytics/factory?range=30d')
    await flushPromises()
    refuse = false
    present(document.querySelector<HTMLElement>('[data-read-again]'), 'Read again').click()
    await flushPromises()

    expect(document.querySelector('[data-factory-notice]')).toBeNull()
  })

  test('a_later_answer_clears_the_row', async () => {
    let refuse = false
    const { router } = await pageAt(FactoryPage, '/analytics/factory', () =>
      refuse ? json({ detail: 'the store is busy' }, 503) : json(dashboard()),
    )
    refuse = true
    await router.push('/analytics/factory?range=30d')
    await flushPromises()
    refuse = false
    await router.push('/analytics/factory?range=90d')
    await flushPromises()

    expect(document.querySelector('[data-factory-notice]')).toBeNull()
  })
})
