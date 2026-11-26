// CF-364: docs/ui.md (The kanban, the Memory page), each entry shows its statement, why, source
// and dates, its guard state, and marks an incomplete or stale entry; Mark reviewed, Edit, Merge
// and Retire change it in place, and a refusal shows under the entry.

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import type { MemoryRecord } from '@/lib/memory'
import { clear, notice } from '@/lib/notice'
import { answer, stubFetch } from '../../support/board'
import { present } from '../../support/present'
import MemoryEntry from '@/components/MemoryEntry.vue'
import { validated } from '../../support/form'

const RECORD: MemoryRecord = {
  repository: 'sample',
  id: 'port-it',
  kind: 'lesson',
  date: '2026-08-01',
  source: 'CF-12',
  statement: 'Port it',
  why: 'The old one broke',
  reviewed: '2026-09-01',
  guard: 'the_port_works',
  guard_state: 'enforced',
  loaded: true,
  stale: false,
  incomplete: false,
  scope: '',
  chars: 40,
  left_out: false,
  superseded_by: '',
  supersedes: '',
  loads: 'every session',
  proposed: false,
  review_due: '2026-12-30',
  filing: 'committed',
  received_by: [],
}

const other = (repository: string, id: string, statement: string): MemoryRecord => ({
  ...RECORD,
  repository,
  id,
  statement,
})

function entry(record: Partial<MemoryRecord> = {}, others: MemoryRecord[] = []) {
  return mount(MemoryEntry, { props: { record: { ...RECORD, ...record }, others } })
}

function due(record: Partial<MemoryRecord> = {}, overdue = true) {
  return mount(MemoryEntry, {
    props: { record: { ...RECORD, ...record }, others: [], variant: 'due' as const, overdue },
  })
}

const button = (wrapper: VueWrapper, name: string) =>
  present(
    wrapper.findAll('button').find((b) => b.text() === name),
    name,
  )
const pills = (wrapper: VueWrapper) => wrapper.findAll('[data-slot="badge"]').map((p) => p.text())

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-10-07T12:00:00Z'))
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  clear()
})

describe('why an entry waits in the review queue (CF-1403)', () => {
  test('names the citations that are gone and a month without a run', () => {
    const gone = due({ stale_cites: ['src/removed.rs', 'old_test'] })
    const idle = due({ unused: true })

    expect(pills(gone)).toContain('Cites gone: src/removed.rs, old_test')
    expect(pills(gone).some((p) => p.startsWith('Review was due'))).toBe(false)
    expect(pills(idle)).toContain('No run received it in 30 days')
  })

  test('keeps the review date for an entry that is only overdue', () => {
    expect(pills(due({ review_due: '2026-09-01' }))).toContain('Review was due 1 Sep')
  })
})

describe('what an entry shows', () => {
  // CF-1195: the closed row is the statement and one quiet line; the rest waits in the open row.
  test('a_closed_row_is_its_statement_and_one_quiet_line', () => {
    const wrapper = entry()
    const summary = wrapper.get('summary')

    expect(summary.text()).toContain('Port it')
    expect(summary.findAll('.text-muted-foreground > *').map((s) => s.text())).toEqual([
      'Lesson',
      'CF-12',
      'review by 30 Dec',
    ])
    expect(wrapper.get('details > div').text()).toContain('Why: The old one broke')
    expect(
      wrapper
        .get('details > div')
        .findAll('.text-muted-foreground > *')
        .map((s) => s.text()),
    ).toEqual(['1 Aug', 'sample', 'No run has received it yet', 'Enforced by the_port_works'])
  })

  // CF-1195: a guard that is gone asks for action, so the closed row says so.
  test('a_guard_that_no_longer_exists_is_flagged_on_the_closed_row', () => {
    const wrapper = entry({ guard_state: 'missing' })

    expect(
      wrapper
        .get('summary')
        .findAll('[data-slot="badge"]')
        .map((p) => p.text()),
    ).toEqual(['Lesson', 'Guard missing: the_port_works'])
  })

  test('an_entry_without_a_guard_says_so_only_when_opened', () => {
    const wrapper = entry({ guard_state: 'none' })

    expect(
      wrapper
        .get('summary')
        .findAll('[data-slot="badge"]')
        .map((p) => p.text()),
    ).toEqual(['Lesson'])
    expect(wrapper.get('details > div').text()).toContain('no guard')
  })

  test('an_entry_whose_guard_is_unknown_shows_no_guard_state', () => {
    expect(pills(entry({ guard_state: '' }))).toEqual(['Lesson'])
  })

  test('an_entry_sessions_do_not_load_says_so_in_the_open_row', () => {
    const wrapper = entry({ loaded: false })

    expect(wrapper.get('summary').text()).not.toContain('not loaded')
    expect(wrapper.get('details > div').text()).toContain('not loaded')
  })

  // CF-1195: a row flags nothing for a missing why or source or a run not yet made.
  test('a_row_flags_no_missing_why_source_or_run', () => {
    const wrapper = entry({ why: '', source: '' })

    expect(
      wrapper
        .get('summary')
        .findAll('[data-slot="badge"]')
        .map((p) => p.text()),
    ).toEqual(['Lesson'])
    expect(wrapper.get('summary').text()).not.toMatch(/no why|no source|no run/i)
    expect(wrapper.get('details > div').text()).toContain('No why recorded')
    expect(wrapper.text()).not.toContain('Why:')
  })
})

describe('reviewing an entry', () => {
  test('mark_reviewed_sends_an_empty_change_and_announces_it', async () => {
    const sent = stubFetch(() => answer({ notice: 'Reviewed port-it', undo: 'u-1' }))
    const wrapper = entry({ repository: 'r#x' })

    await button(wrapper, 'Mark reviewed').trigger('click')
    await flushPromises()

    expect(sent).toEqual([{ method: 'PATCH', url: '/api/memory/r%23x/port-it', body: {} }])
    expect(notice.text).toBe('Reviewed port-it')
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  test('a_refused_review_shows_why_under_the_entry', async () => {
    stubFetch(() => answer({ detail: 'the entry moved' }, 409))
    const wrapper = entry()

    await button(wrapper, 'Mark reviewed').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-slot="field-error"]').text()).toBe('the entry moved')
    expect(wrapper.emitted('changed')).toBeUndefined()
  })

  test('edit_saves_the_changed_fields_and_returns_to_the_entry', async () => {
    const sent = stubFetch(() => answer({ notice: 'Saved' }))
    const wrapper = entry()

    await button(wrapper, 'Edit').trigger('click')
    await wrapper.get('form[aria-label="Edit the entry"] textarea').setValue('Port it all')
    await wrapper.get('form[aria-label="Edit the entry"]').trigger('submit')
    await validated()

    expect(sent).toEqual([
      {
        method: 'PATCH',
        url: '/api/memory/sample/port-it',
        body: {
          kind: 'lesson',
          statement: 'Port it all',
          why: 'The old one broke',
          source: 'CF-12',
          guard: 'the_port_works',
          scope: '',
        },
      },
    ])
    expect(wrapper.find('form').exists()).toBe(false)
  })

  test('a_refused_edit_keeps_the_form_and_shows_why', async () => {
    stubFetch(() => answer({ detail: 'a statement is required' }, 400))
    const wrapper = entry()

    await button(wrapper, 'Edit').trigger('click')
    await wrapper.get('form').trigger('submit')
    await validated()

    expect(wrapper.find('form[aria-label="Edit the entry"]').exists()).toBe(true)
    expect(wrapper.get('[data-slot="field-error"]').text()).toBe('a statement is required')
  })

  test('cancel_returns_to_the_entry', async () => {
    const wrapper = entry()

    await button(wrapper, 'Edit').trigger('click')
    await button(wrapper, 'Cancel').trigger('click')

    expect(wrapper.find('form').exists()).toBe(false)
    expect(button(wrapper, 'Mark reviewed').exists()).toBe(true)
  })

  test('merge_offers_only_other_entries_of_the_same_repository', async () => {
    const wrapper = entry({}, [
      other('sample', 'port-it', 'Port it'),
      other('second', 'b', 'Elsewhere'),
      other('sample', 'c', 'Keep ports'),
      other('sample', 'd', 'Port fast'),
    ])

    await button(wrapper, 'Merge').trigger('click')

    expect(wrapper.findAll('option').map((o) => o.text())).toEqual(['Keep ports', 'Port fast'])
    expect((wrapper.get('select').element as HTMLSelectElement).value).toBe('c')
  })

  test('merge_is_disabled_without_another_entry_in_the_repository', () => {
    const wrapper = entry({}, [other('sample', 'port-it', 'Port it'), other('second', 'b', 'B')])

    expect(button(wrapper, 'Merge').attributes('disabled')).toBeDefined()
  })

  test('merge_sends_the_chosen_entry', async () => {
    const sent = stubFetch(() => answer({ notice: 'Merged' }))
    const wrapper = entry({}, [other('sample', 'c', 'Keep ports'), other('sample', 'd', 'Fast')])

    await button(wrapper, 'Merge').trigger('click')
    await wrapper.get('select').setValue('d')
    await wrapper.get('form[aria-label="Merge the entry"]').trigger('submit')
    await validated()

    expect(sent).toEqual([
      { method: 'POST', url: '/api/memory/sample/port-it/merge', body: { into: 'd' } },
    ])
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  test('retire_waits_for_a_reason_and_sends_it', async () => {
    const sent = stubFetch(() => answer({ notice: 'Retired' }))
    const wrapper = entry()

    await button(wrapper, 'Retire').trigger('click')
    const retire = () =>
      present(
        wrapper.get('form[aria-label="Retire the entry"]').find('button[type="submit"]'),
        'Retire',
      )
    await wrapper.get('form input').setValue('   ')
    const blank = retire().attributes('disabled')
    await wrapper.get('form input').setValue('The port is done')
    await wrapper.get('form').trigger('submit')
    await validated()

    expect(blank).toBeDefined()
    expect(sent).toEqual([
      {
        method: 'POST',
        url: '/api/memory/sample/port-it/retire',
        body: { reason: 'The port is done' },
      },
    ])
  })

  test('opening_a_form_starts_it_without_the_last_refusal_or_reason', async () => {
    stubFetch(() => answer({ detail: 'refused' }, 409))
    const wrapper = entry()
    await button(wrapper, 'Retire').trigger('click')
    await wrapper.get('form input').setValue('Gone')
    await wrapper.get('form').trigger('submit')
    await validated()
    await button(wrapper, 'Cancel').trigger('click')

    await button(wrapper, 'Retire').trigger('click')

    expect(wrapper.find('[data-slot="field-error"]').exists()).toBe(false)
    expect((wrapper.get('form input').element as HTMLInputElement).value).toBe('')
  })

  test('the_actions_are_disabled_while_a_change_is_sent', async () => {
    let reply: (response: Response) => void = () => undefined
    stubFetch(() => new Promise<Response>((resolve) => (reply = resolve)))
    const wrapper = entry()

    await button(wrapper, 'Mark reviewed').trigger('click')
    const during = button(wrapper, 'Mark reviewed').attributes('disabled')
    reply(answer({ notice: '' }))
    await flushPromises()

    expect(during).toBeDefined()
    expect(button(wrapper, 'Mark reviewed').attributes('disabled')).toBeUndefined()
  })
})

// CF-1171-R4
test('an_entry_row_is_closed_and_opens_to_its_why_and_actions', async () => {
  const wrapper = entry({ source: '' }, [other('sample', 'c', 'Keep ports')])
  const details = wrapper.get('[role="listitem"] details')
  const summary = details.get('summary')
  const closed = details.attributes('open')
  const shut = mount(MemoryEntry, {
    props: { record: RECORD, others: [], opened: true },
  })

  expect([
    wrapper.get('[role="listitem"]').attributes('id'),
    closed,
    summary.text().includes('Port it'),
    summary.findAll('[data-slot="badge"]').map((p) => p.text()),
    summary.text().includes('review by 30 Dec'),
    summary.text().includes('Why:'),
    summary.findAll('button').length,
    details.text().includes('Why: The old one broke'),
    details.findAll('button').map((b) => b.text()),
    shut.get('details').attributes('open'),
  ]).toStrictEqual([
    'port-it',
    undefined,
    true,
    ['Lesson'],
    true,
    false,
    0,
    true,
    ['Mark reviewed', 'Edit', 'Merge', 'Retire'],
    '',
  ])
  await flushPromises()
})

// CF-1171-R4
test('a_row_shows_its_review_date_runs_and_filing', () => {
  const plain = entry()
  const marked = entry(
    {
      review_due: '2027-01-05',
      received_by: [
        { run: 'r1', ticket_id: 'CF-7' },
        { run: 'r2', ticket_id: 'CF-7' },
        { run: 'r3', ticket_id: 'CF-9' },
      ],
      left_out: true,
      loaded: false,
      filing: 'pending',
      scope: 'build, crates/**',
      loads: 'build runs; sessions changing crates/**',
    },
    [],
  )
  const superseded = entry({ loaded: false, superseded_by: 'newer' }, [
    other('sample', 'newer', 'Port it all'),
  ])
  const text = (w: VueWrapper, part: string) =>
    w
      .get(part)
      .findAll('.text-muted-foreground > *')
      .map((n) => n.text())

  expect([
    text(plain, 'summary'),
    text(plain, 'details > div').filter((t) => t.includes('run')),
    text(marked, 'summary'),
    text(marked, 'details > div'),
    marked
      .get('summary')
      .findAll('[data-slot="badge"][data-variant="destructive"]')
      .map((n) => n.text()),
    marked.get('details').text().includes('Received by runs of CF-7, CF-9'),
    pills(superseded).filter((t) => t.startsWith('superseded') || t === 'not loaded'),
  ]).toStrictEqual([
    ['Lesson', 'CF-12', 'review by 30 Dec'],
    ['No run has received it yet'],
    ['Lesson', 'CF-12', 'review by 5 Jan 2027', 'Left out', 'Not filed'],
    [
      '1 Aug',
      'sample',
      '3 runs',
      'build runs; sessions changing crates/**',
      'Enforced by the_port_works',
    ],
    ['Left out'],
    true,
    ['superseded by "Port it all"'],
  ])
})

// CF-1171-R4
test('the_form_sends_where_an_entry_loads', async () => {
  const sent = stubFetch(() => answer({ notice: 'Saved' }))
  const wrapper = entry({ scope: 'review' })
  await button(wrapper, 'Edit').trigger('click')
  const form = () => wrapper.get('form[aria-label="Edit the entry"]')
  const select = form().get('select')
  const shown = (select.element as HTMLSelectElement).value
  await select.setValue('paths')
  const submit = () => form().get('button[type="submit"]')
  const blank = submit().attributes('disabled')
  await form().get('input.font-mono').setValue('web/**, docs/*.md')
  await form().trigger('submit')
  await validated()

  expect([
    shown,
    select.findAll('option').map((o) => o.text()),
    blank,
    sent.map((r) => (r.body as { scope: string }).scope),
  ]).toStrictEqual([
    'review',
    [
      'Every session',
      'Every session, first',
      'Spec runs',
      'Build runs',
      'Review runs',
      'Sessions changing a path',
    ],
    '',
    ['web/**, docs/*.md'],
  ])
})

// CF-1429
test('a_row_shows_how_often_and_when_a_run_last_received_it', () => {
  const text = (record: Partial<MemoryRecord>) =>
    entry(record)
      .get('details > div')
      .findAll('.text-muted-foreground > *')
      .map((n) => n.text())
      .filter((t) => t.includes('run'))

  expect([
    text({ received_count: 3, last_received: '2026-11-05' }),
    text({ received_count: 1, last_received: '2026-11-01' }),
    text({ received_count: 0, last_received: '' }),
  ]).toStrictEqual([
    ['3 runs, last received 5 Nov'],
    ['1 run, last received 1 Nov'],
    ['No run has received it yet'],
  ])
})

// CF-1171-R5
test('still_holds_marks_the_entry_reviewed', async () => {
  const sent = stubFetch(() => answer({ notice: 'Reviewed port-it', undo: 'u-1' }))
  const wrapper = due({ review_due: '2026-09-01' })
  const warned = wrapper.findAll('[data-slot="badge"][data-variant="warning"]').map((p) => p.text())
  const id = wrapper.get('article').attributes('id')

  await button(wrapper, 'Still holds').trigger('click')
  await flushPromises()

  expect([warned, id, sent, wrapper.emitted('changed')?.length]).toStrictEqual([
    ['Review was due 1 Sep'],
    undefined,
    [{ method: 'PATCH', url: '/api/memory/sample/port-it', body: {} }],
    1,
  ])
})

// CF-1171-R5
test('add_a_source_waits_for_one_and_sends_it', async () => {
  const sent = stubFetch(() => answer({ notice: 'Saved port-it' }))
  const both = due({ source: '', review_due: '2026-09-01' })
    .findAll('[data-slot="badge"][data-variant="warning"]')
    .map((p) => p.text())
  const wrapper = due({ source: '' }, false)
  const warned = wrapper.findAll('[data-slot="badge"][data-variant="warning"]').map((p) => p.text())
  const holds = wrapper.findAll('button').some((b) => b.text() === 'Still holds')

  await button(wrapper, 'Add a source').trigger('click')
  const save = () => button(wrapper, 'Save and mark reviewed')
  const field = wrapper.get('form[aria-label="Add a source"] input')
  const label = wrapper.get(`label[for="${field.attributes('id') ?? ''}"]`).text()
  await field.setValue('   ')
  const blank = save().attributes('disabled')
  await field.setValue('CF-9')
  const filled = save().attributes('disabled')
  await wrapper.get('form[aria-label="Add a source"]').trigger('submit')
  await validated()

  expect([both, warned, holds, label, blank, filled, sent]).toStrictEqual([
    ['No source', 'Review was due 1 Sep'],
    ['No source'],
    false,
    'Source',
    '',
    undefined,
    [{ method: 'PATCH', url: '/api/memory/sample/port-it', body: { source: 'CF-9' } }],
  ])
})

// CF-1171-R7
test('a_refused_queue_action_shows_why_under_its_item', async () => {
  let reply: (response: Response) => void = () => undefined
  stubFetch(() => new Promise<Response>((resolve) => (reply = resolve)))
  const wrapper = due({ stale: true })

  await button(wrapper, 'Still holds').trigger('click')
  const during = button(wrapper, 'Still holds').attributes('disabled')
  reply(answer({ detail: 'the entry moved' }, 409))
  await flushPromises()

  const refusal = wrapper.get('[data-slot="field-error"]')
  expect([during, refusal.text(), wrapper.emitted('changed')]).toStrictEqual([
    '',
    'the entry moved',
    undefined,
  ])
})

describe('keyboard focus follows a form that opens and closes', () => {
  function attached(record: Partial<MemoryRecord> = {}, variant: 'row' | 'due' = 'row') {
    return mount(MemoryEntry, {
      attachTo: document.body,
      props: {
        record: { ...RECORD, ...record },
        others: [other('sample', 'gate-it', 'Gate it')],
        variant,
      },
    })
  }
  const focused = () => document.activeElement
  const labelOf = (el: Element | null) => el?.getAttribute('aria-label') ?? el?.textContent.trim()

  test('retire_opens_on_its_reason_field_and_cancel_returns_to_retire', async () => {
    const wrapper = attached()
    await button(wrapper, 'Retire').trigger('click')
    await flushPromises()
    const field = [
      focused()?.tagName,
      (focused() as HTMLInputElement | null)?.labels?.[0]?.textContent,
    ]

    await button(wrapper, 'Cancel').trigger('click')
    await flushPromises()

    expect(field).toStrictEqual(['INPUT', 'Why it no longer applies'])
    expect(focused()?.textContent.trim()).toBe('Retire')
    wrapper.unmount()
  })

  test('edit_opens_on_the_statement_and_cancel_returns_to_edit', async () => {
    const wrapper = attached()
    await button(wrapper, 'Edit').trigger('click')
    await flushPromises()
    const field = [
      focused()?.tagName,
      (focused() as HTMLInputElement | null)?.labels?.[0]?.textContent,
    ]

    await button(wrapper, 'Cancel').trigger('click')
    await flushPromises()

    expect(field).toStrictEqual(['TEXTAREA', 'Statement'])
    expect(focused()?.textContent.trim()).toBe('Edit')
    wrapper.unmount()
  })

  test('merge_opens_on_its_target_and_cancel_returns_to_merge', async () => {
    const wrapper = attached()
    await button(wrapper, 'Merge').trigger('click')
    await flushPromises()
    const field = focused()?.tagName

    await button(wrapper, 'Cancel').trigger('click')
    await flushPromises()

    expect(field).toBe('SELECT')
    expect(focused()?.textContent.trim()).toBe('Merge')
    wrapper.unmount()
  })

  test('add_a_source_opens_on_its_field_and_cancel_returns_to_the_button', async () => {
    const wrapper = attached({ source: '' }, 'due')
    await button(wrapper, 'Add a source').trigger('click')
    await flushPromises()
    const field = (focused() as HTMLInputElement | null)?.labels?.[0]?.textContent

    await button(wrapper, 'Cancel').trigger('click')
    await flushPromises()

    expect(field).toBe('Source')
    expect(focused()?.textContent.trim()).toBe('Add a source')
    wrapper.unmount()
  })

  test('a_saved_edit_returns_focus_to_edit', async () => {
    stubFetch(() => Promise.resolve(answer({ ok: true })))
    const wrapper = attached()
    await button(wrapper, 'Edit').trigger('click')
    await flushPromises()

    await wrapper.get('form[aria-label="Edit the entry"]').trigger('submit')
    await validated()

    expect(labelOf(focused())).toBe('Edit')
    wrapper.unmount()
  })

  test('a_saved_source_moves_focus_to_the_rows_item_when_its_button_is_gone', async () => {
    stubFetch(() => Promise.resolve(answer({ ok: true })))
    const wrapper = attached({ source: '' }, 'due')
    await button(wrapper, 'Add a source').trigger('click')
    await flushPromises()
    await wrapper.get('input').setValue('chat')
    await wrapper.setProps({ record: { ...RECORD, source: 'chat' } })

    await wrapper.get('form[aria-label="Add a source"]').trigger('submit')
    await validated()

    expect(focused()?.tagName).not.toBe('BODY')
    expect(wrapper.element.contains(focused())).toBe(true)
    wrapper.unmount()
  })
})

describe('the dates an entry shows', () => {
  // Today is 2026-10-07: a date in this year reads `30 Dec`, one in another year carries it.
  test('a_review_date_reads_in_the_house_form_with_its_year_only_when_not_this_one', () => {
    const closed = (reviewDue: string) =>
      entry({ review_due: reviewDue }).get('summary [title]').text()

    expect([closed('2026-12-30'), closed('2027-01-05')]).toStrictEqual([
      'review by 30 Dec',
      'review by 5 Jan 2027',
    ])
  })

  test('the_full_iso_date_stays_in_the_title_and_out_of_the_visible_text', () => {
    const wrapper = entry({ review_due: '2026-12-30' })
    const row = wrapper.get('summary [title="2026-12-30"]')

    expect(row.text()).toBe('review by 30 Dec')
    expect(wrapper.text()).not.toContain('2026-12-30')
  })

  test('an_overdue_item_and_the_entry_date_use_the_same_form', () => {
    const wrapper = due({ review_due: '2026-09-01', date: '2025-08-01', reviewed: '2026-09-02' })

    expect(wrapper.text()).toContain('Review was due 1 Sep')
    expect(wrapper.text()).toContain('2 Sep')
    expect(wrapper.text()).not.toMatch(/\d{4}-\d{2}-\d{2}/)
    expect(wrapper.find('[title="2026-09-01"]').exists()).toBe(true)
    expect(wrapper.find('[title="2026-09-02"]').exists()).toBe(true)
  })

  test('the_open_row_shows_its_date_and_last_receipt_in_the_house_form', () => {
    const wrapper = entry({ date: '2025-08-01', received_count: 2, last_received: '2026-11-05' })
    const lines = wrapper
      .get('details > div')
      .findAll('.text-muted-foreground > *')
      .map((n) => n.text())

    expect(lines).toContain('1 Aug 2025')
    expect(lines).toContain('2 runs, last received 5 Nov')
    expect(wrapper.find('[title="2025-08-01"]').exists()).toBe(true)
  })
})

describe('the footer of a form', () => {
  const footer = (wrapper: VueWrapper, label: string) =>
    wrapper
      .get(`form[aria-label="${label}"]`)
      .findAll('button')
      .map((b) => b.text())

  test('retire_merge_and_add_a_source_put_cancel_before_the_primary', async () => {
    const wrapper = due({ source: '' }, true)
    const peer = mount(MemoryEntry, {
      props: { record: RECORD, others: [other('sample', 'second', 'Second')] },
    })
    await button(wrapper, 'Add a source').trigger('click')
    await button(peer, 'Merge').trigger('click')
    const merge = footer(peer, 'Merge the entry')
    await peer.get('form[aria-label="Merge the entry"] button[type="button"]').trigger('click')
    await button(peer, 'Retire').trigger('click')

    expect([
      footer(wrapper, 'Add a source'),
      merge,
      footer(peer, 'Retire the entry'),
    ]).toStrictEqual([
      ['Cancel', 'Save and mark reviewed'],
      ['Cancel', 'Merge'],
      ['Cancel', 'Retire'],
    ])
  })
})
