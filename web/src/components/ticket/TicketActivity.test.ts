// @vitest-environment happy-dom

import { afterEach, expect, test, vi } from 'vitest'
import { BASE, form, view } from '../../test/ticketForm'
import { TONE_VARIANTS } from '../../lib/status_tone'

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

const NOW = 1_791_108_660

const RUN = {
  at: NOW - 660,
  sentence: 'flint stopped after 5m, 566,440 tokens',
  kind: 'run',
  text: '',
  run: 'abc123',
  agent: 'flint',
  model: 'recursivesi/flint',
  stage: 'spec',
  iteration: 1,
  outcome: 'stopped',
  exit_code: -15,
  duration: 300,
  tokens: 566_440,
}

async function activity(entries: object[]) {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(NOW * 1000)
  const { page } = await form({ ...(view as object), activity: entries })
  return { page, items: page.find('[aria-label="Activity"]').findAll('li') }
}

// CF-1064-R5, CF-1075-R3: a run's row links its log in a new tab; an entry naming no run has none.
test('a_run_entry_links_its_log', async () => {
  const { page, items } = await activity([
    RUN,
    { at: NOW - 900, sentence: 'Created as a bug', kind: 'created', text: '' },
  ])

  const link = items[0]?.find('a')

  expect(link?.text()).toBe('Log')
  expect(link?.attributes('href')).toBe('/api/runs/abc123/log')
  expect(link?.attributes('target')).toBe('_blank')
  expect(link?.attributes('rel')).toBe('noopener noreferrer')
  expect(items[1]?.find('a').exists()).toBe(false)
  page.unmount()
})

// CF-1075-R3: hand-worked, flint's stopped Spec run of 300 s and 566,440 tokens, 660 s ago, reads
// in one row: flint, recursivesi/flint, Spec, stopped in the quiet tone, "5m · 566.4k tokens",
// Log, "11m ago".
test('a_run_row_shows_its_run_in_one_line', async () => {
  const { page, items } = await activity([
    RUN,
    { ...RUN, run: 'r2', outcome: 'failed', exit_code: 1 },
  ])

  const row = items[0]?.find('[data-run]')
  const words = row?.findAll('span, [data-slot="badge"]').map((s) => s.text())

  expect(words).toEqual(
    expect.arrayContaining([
      'flint',
      'recursivesi/flint',
      'Spec',
      'Stopped',
      '5m · 566.4k tokens',
      '11m ago',
    ]),
  )
  expect(row?.find('[data-slot="badge"]').attributes('data-variant')).toBe(TONE_VARIANTS.quiet)
  expect(items[1]?.find('[data-slot="badge"]').text()).toBe('Failed · exit 1')
  expect(items[1]?.find('[data-slot="badge"]').attributes('data-variant')).toBe(TONE_VARIANTS.error)
  page.unmount()
})

// A run's stage dot keeps the ring every dot keeps, so the lightest and darkest stay in view.
test('a_run_row_draws_its_stage_glyph', async () => {
  const { page, items } = await activity([RUN])

  const glyph = items[0]?.get('[data-run] svg[data-shape]')
  expect([glyph?.attributes('data-shape'), glyph?.classes()]).toEqual([
    'ring',
    expect.arrayContaining(['text-chart-7']),
  ])
  page.unmount()
})

// CF-1075-R4: every entry's age is the right-pushed last part of its row, in faint small text.
test('every_age_sits_at_the_right', async () => {
  const { page, items } = await activity([
    RUN,
    { at: NOW - 900, sentence: 'Created as a bug', kind: 'created', text: '' },
  ])

  for (const item of items) {
    const age = item.find('[data-age]')
    expect(age.classes()).toContain('ml-auto')
    expect(age.text()).toMatch(/ago$/)
  }
  page.unmount()
})

const RUNNING = {
  id: 'r1',
  stage: 'build',
  iteration: 1,
  loop: false,
  started_at: NOW - 60,
  progress: {
    tool_calls: null,
    reads: null,
    changes: null,
    files: null,
    tokens: null,
    last_activity: null,
  },
  memory: null,
  context_at: null,
}

// CF-1371: a ticket with no active run has no message field; one with a run has it.
test('a_message_field_shows_on_a_running_ticket_only', async () => {
  // One ticket at a time: two forms of the same ticket share its one read.
  const offered = async (runs: unknown[]) => {
    const { page } = await form({ ...(view as object), runs })
    const field = page.find('textarea[aria-label="Message to the running agent"]').exists()
    page.unmount()
    return field
  }

  expect(await offered([])).toBe(false)
  expect(await offered([RUNNING])).toBe(true)
})

// CF-1371: sending the field posts its text to the ticket's messages, not its comments.
test('a_message_is_posted_to_the_tickets_messages', async () => {
  const { page, changes, bodies } = await form({ ...(view as object), runs: [RUNNING] })

  await page.find('textarea[aria-label="Message to the running agent"]').setValue('Use files')
  await page.find('button[aria-label="Send message"]').trigger('click')

  expect(changes).toEqual([`POST ${BASE}/messages`])
  expect(bodies).toEqual([{ text: 'Use files' }])
  page.unmount()
})

// CF-1371: a message in the activity reads as the owner's, with its words, and a kept one says it
// waits for the next run.
test('a_message_shows_in_the_activity_with_where_it_went', async () => {
  const { page, items } = await activity([
    {
      at: NOW - 30,
      sentence: 'alex sent a message to the next run',
      kind: 'message',
      text: 'Use files',
    },
  ])

  expect(items[0]?.text()).toContain('alex sent a message to the next run')
  expect(items[0]?.text()).toContain('Use files')
  page.unmount()
})
