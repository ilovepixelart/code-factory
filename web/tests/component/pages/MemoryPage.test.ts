// CF-346: Undo on the Memory page puts the entry back on the page, not only on disk.
// CF-368: a search result opens what it found, and a capped list says how many matched.

import { variantOf } from '../../support/button'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, test, vi } from 'vitest'
import { announce } from '@/lib/notice'
import type { Found, Memory, MemoryRecord, RetiredRecord } from '@/lib/memory'
import { memoryRouter, provideBoard } from '../../support/board'
import { present } from '../../support/present'
import { Toasts } from '../../support/toasts'
import MemoryPage from '@/pages/MemoryPage.vue'
import { labelled, validated } from '../../support/form'

const entry = {
  repository: 'sample',
  id: 'port-it',
  kind: 'rule',
  date: '2026-08-01',
  source: 'chat',
  statement: 'Port it',
  why: '',
  guard: '',
} as const

const retired: RetiredRecord = { ...entry, retired: 'The port is done', merged_into: '' }
const restored: MemoryRecord = {
  ...entry,
  reviewed: '',
  guard_state: 'none',
  loaded: true,
  stale: false,
  incomplete: false,
  scope: '',
  chars: 9,
  left_out: false,
  superseded_by: '',
  supersedes: '',
  loads: 'every session',
  proposed: false,
  review_due: '2026-12-30',
  filing: 'committed',
  received_by: [],
}

function memory(
  unreviewed: MemoryRecord[],
  gone: RetiredRecord[],
  results: Found[] = [],
  matched = results.length,
): Memory {
  return {
    repositories: ['sample'],
    unreviewed,
    rules: [],
    decisions: [],
    lessons: [],
    retired: gone,
    loaded_chars: 0,
    ceiling: 4000,
    results,
    matched,
    page: 1,
    size: 50,
    proposals: [],
    filing: null,
    left_out: [],
    pairs: [],
    review_queue: [],
  }
}

function found(path: string, open: string): Found {
  return { repository: 'sample', path, snippet: 'The gate refuses a push', open }
}

/** The Memory page searched for `gate`, its search answered with `held`. */
async function searched(held: Memory) {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(json(held))),
  )
  const router = memoryRouter([
    { path: '/memory', component: MemoryPage },
    { path: '/:rest(.*)*', component: { template: '<div />' } },
  ])
  await router.push('/memory?q=gate')
  const global = { plugins: [router], provide: provideBoard(), stubs: { teleport: true } }
  const page = mount(MemoryPage, { attachTo: document.body, global })
  await flushPromises()
  await vi.waitFor(() => {
    expect(page.find('#memory-results').exists()).toBe(true)
  })
  return page
}

test('a_search_result_is_a_link_to_what_it_found', async () => {
  const page = await searched(
    memory(
      [],
      [],
      [
        found('.code-factory/tickets/CF-7/brd.md', '/tickets/sample/CF-7'),
        found('docs/notes.md', ''),
      ],
    ),
  )

  const links = page.findAll('#memory-results a').map((a) => [a.text(), a.attributes('href')])
  const text = page.find('#memory-results').text()
  await page.find('#memory-results a').trigger('click')
  await flushPromises()

  expect(links).toStrictEqual([
    ['sample/.code-factory/tickets/CF-7/brd.md', '/tickets/sample/CF-7'],
  ])
  expect(text).toContain('sample/docs/notes.md')
  expect(page.vm.$router.currentRoute.value.path).toBe('/tickets/sample/CF-7')
  page.unmount()
})

test('a_memory_result_links_to_its_entry_on_the_page', async () => {
  const page = await searched(
    memory([restored], [], [found('.code-factory/memory/port-it.md', '#port-it')]),
  )

  const links = page.findAll('#memory-results a').map((a) => a.attributes('href'))
  const target = document.querySelectorAll('[id="port-it"]')
  expect([links, target.length, target[0]?.getAttribute('aria-label')]).toStrictEqual([
    ['#port-it'],
    1,
    'Port it',
  ])
  page.unmount()
})

// CF-1195: the heading counts every file that matched, and the results are paged by the server.
test('a_search_counts_every_match_and_pages_through_them', async () => {
  const ten = Array.from({ length: 10 }, (_, n) => found(`docs/n${String(n)}.md`, ''))
  const asked: string[] = []
  const held = { ...memory([], [], ten, 23), size: 10, page: 2 }
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      asked.push(url)
      return Promise.resolve(json(held))
    }),
  )
  const router = memoryRouter([{ path: '/memory', component: MemoryPage }])
  await router.push('/memory?q=gate&page=2&size=10')
  const global = { plugins: [router], provide: provideBoard(), stubs: { teleport: true } }
  const page = mount(MemoryPage, { attachTo: document.body, global })
  await flushPromises()

  const nav = page.get('#memory-results nav')
  expect([
    asked[0],
    page.get('#results-heading').text(),
    page.get('#memory-results [data-slot="section-description"]').text(),
    nav.get('[data-testid="page-range"]').text(),
    nav.findAll('a[rel]').map((a) => a.attributes('href')),
  ]).toStrictEqual([
    '/api/memory?q=gate&page=2&size=10',
    'Search results, 23',
    'for gate',
    '11 to 20 of 23',
    ['/memory?q=gate&size=10', '/memory?q=gate&page=3&size=10'],
  ])
  page.unmount()
})

// CF-1195: a search with one page of matches shows no page control.
test('a_search_that_fits_one_page_shows_no_page_control', async () => {
  const page = await searched(memory([], [], [found('docs/a.md', '')], 1))

  expect(page.find('#memory-results nav').exists()).toBe(false)
  page.unmount()
})

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

test('an_undo_puts_the_entry_back_on_the_memory_page', async () => {
  let held = memory([], [retired])
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === 'POST' && url === '/api/undo/t-1') {
        held = memory([restored], [])
        return Promise.resolve(json({ notice: 'Restored port-it', undo: null }))
      }
      return Promise.resolve(json(url.startsWith('/api/memory') ? held : {}))
    }),
  )
  const router = memoryRouter([{ path: '/memory', component: MemoryPage }])
  await router.push('/memory')
  const global = { plugins: [router], provide: provideBoard(), stubs: { teleport: true } }
  const page = mount(MemoryPage, { attachTo: document.body, global })
  const toast = mount(Toasts, { attachTo: document.body, global })
  await flushPromises()
  const history = () => document.querySelector('[aria-labelledby="memory-history"]')?.textContent
  await vi.waitFor(() => {
    expect(history()).toContain('Port it')
  })
  announce({ notice: 'Retired port-it', undo: 't-1' })
  await flushPromises()

  const undo = await vi.waitFor(() =>
    present(
      [...document.querySelectorAll('button')].find((b) => b.textContent === 'Undo'),
      'the Undo button',
    ),
  )
  undo.click()
  await flushPromises()

  await vi.waitFor(() => {
    expect(history()).toBeUndefined()
  })
  expect(page.text()).toContain('Port it')
  page.unmount()
  toast.unmount()
})

// CF-485-R2: docs/design.md names the `default` Button for the main action, as the owner chose for the
// Agents page (CF-480).
test('the_memory_page_main_actions_are_primary_buttons', async () => {
  const other: MemoryRecord = { ...restored, id: 'gate-it', statement: 'Gate it' }
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(json(memory([restored, other], [])))),
  )
  const router = memoryRouter([{ path: '/memory', component: MemoryPage }])
  await router.push('/memory')
  const global = { plugins: [router], provide: provideBoard(), stubs: { teleport: true } }
  const page = mount(MemoryPage, { attachTo: document.body, global })
  await flushPromises()
  const named = (scope: { findAll: typeof page.findAll }, text: string) => {
    const found = scope.findAll('button').find((b) => b.text().trim() === text)
    if (!found) throw new Error(`the ${text} button is missing`)
    return found
  }

  const add = named(page, 'Add an entry')
  await add.trigger('click')
  const addSubmit = page.get('form[aria-label="Add an entry"] button[type="submit"]')
  await named(page.get('[role="listitem"][aria-label="Port it"]'), 'Merge').trigger('click')
  const mergeSubmit = page.get('form[aria-label="Merge the entry"] button[type="submit"]')
  await named(page.get('[role="listitem"][aria-label="Gate it"]'), 'Retire').trigger('click')
  const retireSubmit = page.get('form[aria-label="Retire the entry"] button[type="submit"]')

  expect([add, addSubmit, mergeSubmit, retireSubmit].map((b) => variantOf(b))).toStrictEqual([
    'default',
    'default',
    'default',
    'default',
  ])
  page.unmount()
})

/** An active entry `id`, stated as its id, with `fields` over a reviewed rule of 10 characters. */
function rec(id: string, fields: Partial<MemoryRecord> = {}): MemoryRecord {
  return { ...restored, id, statement: id, reviewed: '2026-10-01', chars: 10, ...fields }
}

const proposal = {
  repository: 'sample',
  action: 'retire',
  id: 'gate-it',
  statement: 'Gate it',
  reason: 'its guard enforces it',
} as const

/** The Memory page mounted over `held`. */
async function opened(held: Memory) {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(json(held))),
  )
  const router = memoryRouter([{ path: '/memory', component: MemoryPage }])
  await router.push('/memory')
  const global = { plugins: [router], provide: provideBoard(), stubs: { teleport: true } }
  const page = mount(MemoryPage, { attachTo: document.body, global })
  await flushPromises()
  return page
}

/** The page's parts in order: each section's title, and `meter` for the meter. */
const parts = (page: Awaited<ReturnType<typeof opened>>) =>
  page
    .findAll('h2[data-slot="section-title"], [data-slot="card-title"] h2, [role="meter"]')
    .map((n) => (n.attributes('role') === 'meter' ? 'meter' : n.text().replace(/, \d+$/, '')))

const regionOf = (page: Awaited<ReturnType<typeof opened>>, title: string) =>
  present(
    page.findAll('section').find(
      (s) =>
        s
          .find('h2')
          .text()
          .replace(/, \d+$/, '') === title,
    ),
    `the ${title} section`,
  )

const pair = {
  repository: 'sample',
  one: 'later',
  other: 'fresh',
  one_statement: 'later',
  other_statement: 'fresh',
  terms: ['branch', 'merge'],
  contradicts: true,
}

// CF-1171-R1
test('the_queues_come_first_and_only_while_they_hold_something', async () => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-10-07T12:00:00Z'))
  const fresh = rec('fresh', { date: '2026-10-09' })
  const old = rec('old', { review_due: '2026-08-01' })
  const later = rec('later', { review_due: '2026-09-01', date: '2026-06-03' })
  const sourceless = rec('sourceless', { source: '', review_due: '2026-12-05' })
  const asked = rec('asked', { proposed: true, loaded: false, source: '' })
  const quiet = await opened(memory([fresh], []))
  const quietParts = parts(quiet)
  quiet.unmount()
  const busy = await opened({
    ...memory([later, fresh, sourceless, old, asked], []),
    proposals: [proposal],
    pairs: [pair],
    review_queue: [old, later],
  })

  const due = regionOf(busy, 'Review due')
    .findAll('li article')
    .map((a) => a.attributes('aria-label'))
  const flag = regionOf(busy, 'Flagged by consolidate')
  expect([quietParts, parts(busy), due]).toStrictEqual([
    ['meter', 'To review', 'Core'],
    [
      'meter',
      'Proposed by agents',
      'Flagged by consolidate',
      'Proposed by consolidate',
      'Review due',
      'Core',
    ],
    ['old', 'later', 'sourceless'],
  ])
  expect([
    flag.get('[data-slot="badge"][data-variant="warning"]').text(),
    flag.text().includes('both say branch, merge'),
    flag.findAll('.md\\:grid-cols-2 > div').map((d) => d.text()),
    regionOf(busy, 'Core')
      .findAll('[role="listitem"][aria-label]')
      .map((a) => a.attributes('aria-label')),
  ]).toStrictEqual([
    'Contradicts',
    true,
    ['older, 3 Junlater', 'newer, 9 Octfresh'],
    ['later', 'fresh', 'sourceless', 'old'],
  ])
  busy.unmount()
})

// CF-1171-R1
test('a_long_queue_shows_three_and_a_button_for_the_rest', async () => {
  const stale = ['a', 'b', 'c', 'd', 'e'].map((id) => rec(id))
  const page = await opened({ ...memory(stale, []), review_queue: stale })
  const queue = () => regionOf(page, 'Review due')
  const shown = () => queue().findAll('li article').length
  const before = shown()
  const more = present(
    queue()
      .findAll('button')
      .find((b) => b.text() === 'Show 2 more'),
    'Show 2 more',
  )

  await more.trigger('click')

  expect([before, shown(), queue().text().includes('more')]).toStrictEqual([3, 5, false])
  page.unmount()
})

// CF-1171-R1
test('with_nothing_waiting_one_empty_state_says_so', async () => {
  const flagged = await opened({ ...memory([rec('later'), rec('fresh')], []), pairs: [pair] })
  const flaggedEmpty = flagged.text().includes('Nothing to review')
  flagged.unmount()
  const page = await opened(memory([rec('fresh')], []))

  // The owner: the empty state sits in its section's Card, a short title over its sentence.
  const empties = page
    .findAll('[data-section] [data-slot="empty"]')
    .map((p) => [
      p.get('[data-slot="empty-title"]').text(),
      p.get('[data-slot="empty-description"]').text(),
    ])
  expect([flaggedEmpty, empties, parts(page)]).toStrictEqual([
    false,
    [['Nothing to review', 'No proposals, no flags, nothing due for review.']],
    ['meter', 'To review', 'Core'],
  ])
  page.unmount()
})

/** The Memory page over `held`, each change answered and recorded. */
async function acting(held: Memory) {
  const sent: { method: string; url: string; body: unknown }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      if (init?.method && init.method !== 'GET') {
        sent.push({
          method: init.method,
          url,
          body: JSON.parse((init.body as string | undefined) ?? '{}') as unknown,
        })
        return Promise.resolve(json({ notice: 'Done', undo: 'u-1' }))
      }
      return Promise.resolve(json(held))
    }),
  )
  const router = memoryRouter([{ path: '/memory', component: MemoryPage }])
  await router.push('/memory')
  const global = { plugins: [router], provide: provideBoard(), stubs: { teleport: true } }
  const page = mount(MemoryPage, { attachTo: document.body, global })
  await flushPromises()
  return { page, sent }
}

const press = async (page: Awaited<ReturnType<typeof opened>>, region: string, name: string) => {
  await present(
    regionOf(page, region)
      .findAll('button')
      .find((b) => b.text() === name),
    name,
  ).trigger('click')
  await flushPromises()
}

// CF-1171-R1
test('an_agent_proposal_is_approved_or_dismissed_from_its_queue', async () => {
  const asked = rec('asked', {
    proposed: true,
    loaded: false,
    source: 'agent',
    why: 'A guess cost a day',
    loads: 'build runs',
  })
  const { page, sent } = await acting(memory([asked, rec('kept')], []))
  const queue = regionOf(page, 'Proposed by agents')
  const shown = [
    queue.text().includes('Why: A guess cost a day'),
    queue.text().includes('would load in build runs'),
  ]

  await press(page, 'Proposed by agents', 'Approve')
  await press(page, 'Proposed by agents', 'Dismiss')

  expect([shown, sent.map((r) => [r.method, r.url])]).toStrictEqual([
    [true, true],
    [
      ['POST', '/api/memory/sample/asked/approve'],
      ['POST', '/api/memory/sample/asked/dismiss'],
    ],
  ])
  page.unmount()
})

// A proposal is drawn as the entries below it are (one Item row with its title), not in a
// larger type of its own; its queue says plainly that it loads nowhere yet.
test('an_agent_proposal_is_a_row_like_the_entries', async () => {
  const asked = rec('asked', { proposed: true, loaded: false, source: 'agent', loads: 'builds' })
  const { page } = await acting(memory([asked, rec('kept')], []))
  const queue = regionOf(page, 'Proposed by agents')

  expect([
    queue.find('[data-slot="item"] [data-slot="item-title"]').text(),
    queue.text().includes('Nothing here loads until you approve it'),
  ]).toStrictEqual(['asked', true])
  page.unmount()
})

// CF-1171-R1
test('newer_supersedes_older_sends_the_older_id', async () => {
  const older = rec('later', { date: '2026-06-03' })
  const newer = rec('fresh', { date: '2026-10-09' })
  const { page, sent } = await acting({ ...memory([newer, older], []), pairs: [pair] })

  await press(page, 'Flagged by consolidate', 'Newer supersedes older')

  expect(sent).toStrictEqual([
    { method: 'PATCH', url: '/api/memory/sample/fresh', body: { supersedes: 'later' } },
  ])
  page.unmount()
})

const SIZED = [
  rec('one', { chars: 1200 }),
  rec('two', { chars: 300 }),
  rec('specced', { scope: 'spec', chars: 40 }),
  rec('judged', { scope: 'review', chars: 70 }),
  rec('pathed', { scope: 'web/**', chars: 25 }),
  rec('held', { loaded: false, guard_state: 'enforced', chars: 40 }),
]

// CF-1171-R2, CF-1195: the sentence and its bar alone while the store is well within its budget.
test('the_meter_is_a_flat_section_of_its_sentence_and_bar_while_the_store_is_small', async () => {
  const page = await opened({
    ...memory(SIZED, []),
    loaded_chars: 1500,
    ceiling: 4000,
  })

  const meter = page.get('[role="meter"]')
  expect([meter.attributes('aria-valuenow'), meter.attributes('aria-valuemax')]).toStrictEqual([
    '1500',
    '4000',
  ])
  // The meter is flat like the page's sections, its sentence in the heading row over its bar.
  expect([
    meter.attributes('data-section'),
    meter.get('p').text(),
    meter.find('[data-slot="progress"]').exists(),
    meter.text().includes('Nothing is left out.'),
  ]).toStrictEqual(['', 'Every session loads 1,500 of 4,000 characters', true, false])
  page.unmount()
})

// CF-1195: the box returns at 80 percent of the budget, with what each role adds.
test('the_meter_opens_into_its_box_near_the_budget', async () => {
  const below = await opened({ ...memory(SIZED, []), loaded_chars: 3199, ceiling: 4000 })
  const belowBox = below.get('[role="meter"]').text().includes('Nothing is left out.')
  below.unmount()
  const page = await opened({ ...memory(SIZED, []), loaded_chars: 3200, ceiling: 4000 })

  const meter = page.get('[role="meter"]')
  expect(belowBox).toBe(false)
  expect(meter.text()).toContain('Every session loads 3,200 of 4,000 characters')
  expect(meter.text()).toContain(
    'Spec runs add 40. Review runs add 70. Sessions changing a path add up to 25. Not loaded: 1 entry.',
  )
  expect(meter.text()).toContain('Nothing is left out.')
  expect(meter.text()).not.toContain('Build runs')
  expect(meter.find('.text-destructive').exists()).toBe(false)
  page.unmount()
})

// CF-1171-R2
test('the_meter_turns_error_above_the_ceiling', async () => {
  const at = await opened({ ...memory([rec('one')], []), loaded_chars: 4000, ceiling: 4000 })
  const above = 'Above the ceiling: retire or merge entries.'
  const atError = at.get('[role="meter"]').text().includes(above)
  at.unmount()
  const over = await opened({ ...memory([rec('one')], []), loaded_chars: 4001, ceiling: 4000 })

  const meter = over.get('[role="meter"]')
  expect([
    atError,
    meter.get('[data-slot="progress"]').attributes('aria-valuenow'),
    meter.text().includes(above),
  ]).toStrictEqual([false, '100', true])
  over.unmount()
})

// CF-1400
test('the_meter_says_when_rules_and_decisions_exceed_the_budget', async () => {
  const fits = await opened({ ...memory([rec('one')], []), rules_over: 0 })
  const fitsText = fits.get('[role="meter"]').text()
  fits.unmount()
  const over = await opened({ ...memory([rec('one')], []), rules_over: 1500 })

  const said = over.get('[role="meter"] .text-destructive').text()

  expect(fitsText).not.toContain('over the budget')
  expect(said).toBe(
    'Rules and decisions take 1,500 characters over the budget: merge, scope or retire one.',
  )
  over.unmount()
})

// CF-1171-R2: an entry left out opens the box whatever the size.
test('the_meter_names_what_the_budget_leaves_out', async () => {
  const page = await opened({
    ...memory(
      [rec('kept'), rec('cut', { statement: 'Cut rule', loaded: false, left_out: true })],
      [],
    ),
    left_out: [{ repository: 'sample', id: 'cut' }],
    loaded_chars: 100,
    ceiling: 4000,
  })

  const meter = page.get('[role="meter"]')
  const links = meter.findAll('a[href^="#"]').map((a) => [a.text(), a.attributes('href')])
  expect([
    links,
    meter.text().includes('Left out over the budget:'),
    meter.text().includes('Nothing is left out.'),
    meter.text().includes('Not loaded: 0 entries.'),
  ]).toStrictEqual([[['Cut rule', '#cut']], true, false, true])
  page.unmount()
})

// CF-1171-R3
test('entries_are_grouped_by_where_they_load', async () => {
  const page = await opened(
    memory(
      [
        rec('core one', { chars: 100 }),
        rec('judged', { scope: 'review', chars: 30 }),
        rec('held', { loaded: false, guard_state: 'enforced' }),
        rec('core two', { scope: 'core', chars: 50 }),
        rec('cut', { loaded: false, left_out: true, chars: 5 }),
        rec('specced', { scope: 'spec, review', chars: 20 }),
        rec('built', { scope: 'web/**, build', chars: 15 }),
        rec('pathed', { scope: 'web/**', chars: 12 }),
        rec('replaced', { loaded: false, superseded_by: 'core one' }),
        rec('asked', { proposed: true, loaded: false }),
      ],
      [],
    ),
  )

  const titles = ['Core', 'Spec', 'Build', 'Review', 'Paths', 'Not loaded']
  const groups = titles.map((title) => {
    const region = regionOf(page, title)
    return [
      title,
      region.get('[data-slot="section-description"]').text(),
      region.findAll('[role="listitem"][aria-label]').map((a) => a.attributes('aria-label')),
    ]
  })
  const closed = regionOf(page, 'Not loaded').attributes('data-state')
  expect([groups, parts(page), closed]).toStrictEqual([
    [
      ['Core', 'every session, 155 characters', ['core one', 'core two', 'cut']],
      ['Spec', 'spec runs, 20 characters', ['specced']],
      ['Build', 'build runs, 15 characters', ['built']],
      ['Review', 'review runs, 30 characters', ['judged']],
      ['Paths', 'sessions changing a matching path, up to 12 characters', ['pathed']],
      ['Not loaded', 'a test enforces each, or another entry supersedes it', ['held', 'replaced']],
    ],
    ['meter', 'Proposed by agents', ...titles],
    'closed',
  ])
  page.unmount()
})

// CF-1429
test('an_archive_entry_is_listed_under_a_group_naming_the_archive', async () => {
  const page = await opened(
    memory([rec('index me', { scope: 'archive', loads: 'searched on demand' }), rec('plain')], []),
  )

  const region = regionOf(page, 'Archive')
  expect([
    region.get('[data-slot="section-description"]').text(),
    region.findAll('[role="listitem"][aria-label]').map((a) => a.attributes('aria-label')),
    page.findAll('section h2').some((h) => h.text().startsWith('Paths')),
  ]).toStrictEqual(['searched on demand, listed in the index of recall', ['index me'], false])
  page.unmount()
})

// CF-1171-R6
test('history_names_a_merge_into_a_retired_entry_by_its_statement', async () => {
  const kept: RetiredRecord = { ...retired, id: 'kept', statement: 'Keep ports small' }
  const merged: RetiredRecord = {
    ...retired,
    id: 'gone',
    statement: 'Ports small',
    merged_into: 'kept',
  }
  const page = await opened(memory([], [merged, { ...kept, retired: 'done' }]))

  const history = page.get('section[aria-labelledby="memory-history"]')
  expect([
    history.attributes('data-state'),
    history.get('h2').text(),
    history.text().includes('into "Keep ports small"'),
  ]).toStrictEqual(['closed', 'History, 2', true])
  page.unmount()
})

// CF-1171-R6
test('a_filing_that_did_not_land_shows_above_the_queues', async () => {
  const zone = process.env.TZ
  process.env.TZ = 'UTC'
  const page = await opened({
    ...memory([rec('due', { stale: true })], []),
    filing: { worktree: 'tickets-1171', outcome: 'the gate failed', at: 1_794_310_920 },
  })
  process.env.TZ = zone

  const alert = page.get('[role="alert"]')
  const order = page
    .findAll('[role="alert"], h2[data-slot="section-title"], [data-slot="card-title"] h2')
    .map((n) => n.text().slice(0, 10))
  expect([alert.attributes('data-slot'), alert.text(), order[0]]).toStrictEqual([
    'alert',
    'Memory changes were not filed at 11:42:00: the gate failed. code-factory land tickets-1171 lands them by hand.',
    'Memory cha',
  ])
  page.unmount()
})

// CF-1171-R4
test('an_address_naming_an_entry_opens_its_row_and_its_closed_group', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve(
        json(memory([rec('held', { loaded: false, guard_state: 'enforced' }), rec('kept')], [])),
      ),
    ),
  )
  const router = memoryRouter([{ path: '/memory', component: MemoryPage }])
  await router.push('/memory#held')
  const global = { plugins: [router], provide: provideBoard(), stubs: { teleport: true } }
  const page = mount(MemoryPage, { attachTo: document.body, global })
  await flushPromises()

  const open = (selector: string) => document.querySelector(selector)?.hasAttribute('open')
  expect([
    document.querySelector('section[aria-labelledby="memory-off"]')?.getAttribute('data-state') ===
      'open',
    open('[id="held"] details'),
    open('[id="kept"] details'),
  ]).toStrictEqual([true, true, false])
  page.unmount()
})

// CF-1171-R7
test('a_refused_queue_change_shows_why_under_its_item', async () => {
  let reply: (response: Response) => void = () => undefined
  const asked = rec('asked', { proposed: true, loaded: false })
  vi.stubGlobal(
    'fetch',
    vi.fn((_url: string, init?: RequestInit) =>
      init?.method === 'POST'
        ? new Promise<Response>((resolve) => (reply = resolve))
        : Promise.resolve(json(memory([asked], []))),
    ),
  )
  const router = memoryRouter([{ path: '/memory', component: MemoryPage }])
  await router.push('/memory')
  const global = { plugins: [router], provide: provideBoard(), stubs: { teleport: true } }
  const page = mount(MemoryPage, { attachTo: document.body, global })
  await flushPromises()
  const queue = () => regionOf(page, 'Proposed by agents')
  const approve = () =>
    present(
      queue()
        .findAll('button')
        .find((b) => b.text() === 'Approve'),
      'Approve',
    )

  await approve().trigger('click')
  const during = approve().attributes('disabled')
  reply(json({ detail: 'asked is not proposed' }, 400))
  await flushPromises()

  expect([
    during,
    queue().get('article [data-slot="field-error"]').text(),
    approve().attributes('disabled'),
  ]).toStrictEqual(['', 'asked is not proposed', undefined])
  page.unmount()
})

// CF-1171-R7
test('a_failed_read_shows_why_and_reads_again', async () => {
  let fail = true
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve(
        fail ? json({ detail: 'the store is unreadable' }, 500) : json(memory([rec('kept')], [])),
      ),
    ),
  )
  const router = memoryRouter([{ path: '/memory', component: MemoryPage }])
  await router.push('/memory')
  const global = { plugins: [router], provide: provideBoard(), stubs: { teleport: true } }
  const page = mount(MemoryPage, { attachTo: document.body, global })
  await flushPromises()
  const said = page.text().includes('the store is unreadable')
  const again = present(
    page.findAll('button').find((b) => b.text() === 'Read again'),
    'Read again',
  )
  fail = false
  await again.trigger('click')
  await flushPromises()

  expect([said, page.find('[role="meter"]').exists()]).toStrictEqual([true, true])
  page.unmount()
})

/** The Memory page at `address`, over `held`. */
async function at(address: string, held: Memory) {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(json(held))),
  )
  const router = memoryRouter([{ path: '/memory', component: MemoryPage }])
  await router.push(address)
  const global = { plugins: [router], provide: provideBoard(), stubs: { teleport: true } }
  const page = mount(MemoryPage, { attachTo: document.body, global })
  await flushPromises()
  return { page, router }
}

const ids = (page: Awaited<ReturnType<typeof opened>>, title: string) =>
  regionOf(page, title)
    .findAll('[role="listitem"][aria-label]')
    .map((a) => a.attributes('aria-label'))

// CF-1195: the entries without a why are counted by the meter line, not flagged one by one.
test('the_entries_without_a_why_are_counted_and_listed_alone_on_request', async () => {
  const held = memory(
    [
      rec('bare one', { why: '' }),
      rec('said', { why: 'it broke' }),
      rec('bare two', { why: '  ' }),
      rec('asked', { why: '', proposed: true, loaded: false }),
    ],
    [],
  )
  const all = await at('/memory', held)
  const count = all.page.get('[role="meter"] a')
  const shown = [count.text(), count.attributes('aria-pressed'), ids(all.page, 'Core')]
  const rowPills = all.page.get('[role="listitem"][aria-label="bare one"] summary').text()
  all.page.unmount()
  const only = await at('/memory?why=none', held)
  const pressed = only.page.get('[role="meter"] a')

  expect(shown).toStrictEqual(['2 without a why', 'false', ['bare one', 'said', 'bare two']])
  expect(rowPills).not.toContain('no why')
  expect([
    pressed.attributes('aria-pressed'),
    pressed.attributes('href'),
    ids(only.page, 'Core'),
  ]).toStrictEqual(['true', '/memory', ['bare one', 'bare two']])
  only.page.unmount()
})

// CF-1195: with every entry said why, nothing is counted or filtered.
test('no_count_shows_while_every_entry_says_why', async () => {
  const { page } = await at('/memory', memory([rec('said', { why: 'it broke' })], []))

  expect(page.find('[role="meter"] a').exists()).toBe(false)
  page.unmount()
})

// CF-1195: a group is paged at 50 in the browser, by its own address keys.
test('a_group_shows_50_entries_and_pages_the_rest', async () => {
  const many = Array.from({ length: 120 }, (_, n) =>
    rec(`entry ${String(n).padStart(3, '0')}`, { why: 'x' }),
  )
  const first = await at('/memory', memory(many, []))
  const firstIds = ids(first.page, 'Core')
  const links = first.page
    .get('nav[aria-label="Pages of Core entries"]')
    .findAll('a[rel]')
    .map((a) => a.attributes('href'))
  first.page.unmount()
  const last = await at('/memory?core-page=3', memory(many, []))

  expect([firstIds.length, firstIds[0], firstIds[49], links]).toStrictEqual([
    50,
    'entry 000',
    'entry 049',
    ['/memory?core-page=2'],
  ])
  expect(ids(last.page, 'Core')).toStrictEqual(many.slice(100).map((r) => r.id))
  expect(regionOf(last.page, 'Core').get('h2').text()).toBe('Core, 120')
  last.page.unmount()
})

// CF-1195: an address naming an entry on a later page shows that page.
test('an_address_naming_an_entry_on_a_later_page_shows_that_page', async () => {
  const many = Array.from({ length: 120 }, (_, n) =>
    rec(`entry ${String(n).padStart(3, '0')}`, { why: 'x' }),
  )
  const { page, router } = await at('/memory#entry%20075', memory(many, []))

  await flushPromises()
  expect([
    router.currentRoute.value.query,
    ids(page, 'Core')[0],
    document.querySelector('[id="entry 075"] details')?.hasAttribute('open'),
  ]).toStrictEqual([{ 'core-page': '2' }, 'entry 050', true])
  page.unmount()
})

// CF-1195: History shows only once an entry has been retired.
test('history_is_absent_until_an_entry_is_retired', async () => {
  const none = await at('/memory', memory([rec('kept')], []))
  const without = none.page.find('[aria-labelledby="memory-history"]').exists()
  none.page.unmount()
  const some = await at('/memory', memory([rec('kept')], [retired]))

  expect([without, some.page.find('[aria-labelledby="memory-history"]').exists()]).toStrictEqual([
    false,
    true,
  ])
  some.page.unmount()
})

test('add_an_entry_opens_on_its_statement_and_cancel_returns_to_the_button', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(json(memory([restored], [])))),
  )
  const router = memoryRouter([{ path: '/memory', component: MemoryPage }])
  await router.push('/memory')
  const global = { plugins: [router], provide: provideBoard(), stubs: { teleport: true } }
  const page = mount(MemoryPage, { attachTo: document.body, global })
  await flushPromises()
  const named = (text: string) => {
    const found = page.findAll('button').find((b) => b.text().trim() === text)
    if (!found) throw new Error(`the ${text} button is missing`)
    return found
  }

  await named('Add an entry').trigger('click')
  await flushPromises()
  const opened = [
    document.activeElement?.tagName,
    (document.activeElement as HTMLTextAreaElement | null)?.labels[0]?.textContent,
  ]
  await named('Cancel').trigger('click')
  await flushPromises()

  expect(opened).toStrictEqual(['TEXTAREA', 'Statement'])
  expect(document.activeElement?.textContent.trim()).toBe('Add an entry')
  page.unmount()
})

test('add_an_entry_shows_the_first_repository_as_the_one_it_adds_to', async () => {
  const posts: unknown[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn((_url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        posts.push(JSON.parse(init.body as string))
        return Promise.resolve(json({ notice: 'Added', undo: null }))
      }
      return Promise.resolve(
        json({ ...memory([restored], []), repositories: ['sample', 'second'] }),
      )
    }),
  )
  const router = memoryRouter([{ path: '/memory', component: MemoryPage }])
  await router.push('/memory')
  const global = { plugins: [router], provide: provideBoard(), stubs: { teleport: true } }
  const page = mount(MemoryPage, { attachTo: document.body, global })
  await flushPromises()

  await present(
    page.findAll('button').find((b) => b.text().trim() === 'Add an entry'),
    'Add an entry',
  ).trigger('click')
  const select = page.get('select#memory-add-repository')
  const shown = (select.element as HTMLSelectElement).value
  await page.get('textarea').setValue('Gate it')
  await labelled(page, 'Source').setValue('CF-1')
  await page.get('form[aria-label="Add an entry"]').trigger('submit')
  await validated()

  expect(shown).toBe('sample')
  expect(posts).toMatchObject([{ repository: 'sample', statement: 'Gate it' }])
  page.unmount()
})
