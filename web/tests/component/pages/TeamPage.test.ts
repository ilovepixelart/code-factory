// CF-1162, CF-1193: the Team page reads the team every 3 seconds, says why a first read failed and
// offers to read again, keeps the last rows under the server's reason when a later read fails, and
// opens a row's peek, closed by Escape or its Close button, focus returning to the row.

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { ref } from 'vue'
import { ATTENTION, pageTitle } from '@/lib/attention'
import { answer, memoryRouter, stubFetch } from '../../support/board'
import { teamNow, teamPeek, teamRow } from '../../support/team'
import TeamPage from '@/pages/TeamPage.vue'
import { Tick02Icon, UserGroupIcon } from '@hugeicons/core-free-icons'
import { draws } from '../../support/icons'

process.env.TZ = 'UTC'

let view: VueWrapper | undefined

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] })
})
afterEach(() => {
  view?.unmount()
  view = undefined
  vi.useRealTimers()
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

const read = () =>
  teamNow({
    working: [teamRow()],
    needs_you: [
      teamRow({
        key: 'row-2',
        state: 'owner',
        ticket: { repository: 'sample', id: 'CF-2', title: 'Pick one' },
      }),
    ],
  })
const withPeek = () => ({ ...read(), peek: { 'sample/CF-1': teamPeek() } })
const busy = () => answer({ detail: 'the board is busy' }, 503)
const text = () => document.body.textContent.replace(/\s+/g, ' ')
function rowButton(key: string): HTMLElement {
  const button = document.querySelector<HTMLElement>(`[data-row="${key}"] button`)
  if (!button) throw new Error(`no row ${key}`)
  return button
}
const peekOpen = () => document.querySelector('aside[aria-labelledby="team-peek-title"]') !== null

async function mounted(reply: (call: number) => Response) {
  document.body.innerHTML = '<div id="header-controls"></div><div id="app"></div>'
  let calls = 0
  stubFetch(() => {
    calls += 1
    return reply(calls)
  })
  view = mount(TeamPage, {
    attachTo: '#app',
    global: { plugins: [memoryRouter()], provide: { [ATTENTION as symbol]: { count: ref(6) } } },
  })
  await flushPromises()
  return () => calls
}

const tick = async () => {
  await vi.advanceTimersByTimeAsync(3000)
  await flushPromises()
}

test('a_refused_first_read_shows_the_reason_and_reads_again_on_request', async () => {
  const calls = await mounted((n) => (n === 1 ? busy() : answer(read())))
  expect(text()).toContain('the board is busy')
  expect(text()).not.toContain('Showing the last read')
  document.querySelector<HTMLElement>('[data-read-again]')?.click()
  await flushPromises()

  expect(calls()).toBe(2)
  expect(text()).not.toContain('the board is busy')
  expect(text()).toContain('Build the thing')
})

test('a_later_refusal_keeps_the_rows_and_says_when_they_were_read', async () => {
  await mounted((n) => (n === 1 ? busy() : n === 2 ? answer(read()) : busy()))
  document.querySelector<HTMLElement>('[data-read-again]')?.click()
  await flushPromises()
  await tick()

  expect(text()).toContain(
    'The Team page could not be read: the board is busy. Showing the last read, at 12:00.',
  )
  expect(text()).toContain('Build the thing')
  expect(text()).toContain('Pick one')
})

const unreachable = (): Response => {
  throw new TypeError('Failed to fetch')
}

test('a_first_read_the_board_does_not_answer_says_so_in_words', async () => {
  await mounted(unreachable)

  expect(text()).toContain('The board did not answer; try again.')
  expect(text()).not.toContain('Failed to fetch')
})

// The header says the board did not answer and when the page was last read; the page does not
// say it again.
test('a_later_read_the_board_does_not_answer_keeps_the_rows_without_a_line_of_its_own', async () => {
  await mounted((n) => (n === 1 ? answer(read()) : unreachable()))
  await tick()

  expect(text()).not.toContain('could not be read')
  expect(text()).toContain('Build the thing')
})

test('a_later_answer_takes_the_failure_line_away', async () => {
  await mounted((n) => (n === 2 ? busy() : answer(read())))
  await tick()
  expect(text()).toContain('Showing the last read')
  await tick()

  expect(text()).not.toContain('could not be read')
})

// The owner: each group's count is in its section's title alone; the header does not repeat them,
// and the tab title is the Inbox count every page shows, not one of the Team page's own.
test('each_group_is_counted_by_its_title_alone_and_the_tab_keeps_the_inbox_count', async () => {
  await mounted(() => answer(read()))
  const titles = [...document.querySelectorAll('section h2')].map((h) =>
    h.textContent.replace(/\s+/g, ' ').trim(),
  )
  expect(titles).toEqual([
    'Today against this cycle',
    'Waiting on you, 1',
    'Waiting, 0',
    'Working, 1',
    'Done today, 0',
    'Stale, 0',
  ])
  expect(document.getElementById('header-controls')?.textContent.trim()).toBe('')
  expect(pageTitle.value).toBe('')
})

// What waits on the owner is answered in the Inbox: the group links there with the Inbox's own
// count, the number the sidebar shows.
test('the_waiting_on_you_group_links_to_the_inbox_with_its_count', async () => {
  await mounted(() => answer(read()))
  const link = document
    .getElementById('team-needs_you')
    ?.closest('[data-section]')
    ?.querySelector('[data-slot="section-action"] a')

  expect([link?.getAttribute('href'), link?.textContent.replace(/\s+/g, ' ').trim()]).toEqual([
    '/inbox',
    'Open the Inbox 6',
  ])
})

// Each section's hint reads as words, the cycle named as the server words it.
test('the_stage_times_and_done_today_hints_read_as_plain_words', async () => {
  await mounted(() => answer(read()))
  const hint = (id: string) =>
    document
      .getElementById(id)
      ?.closest('[data-section]')
      ?.querySelector('[data-slot="section-description"]')
      ?.textContent.trim()

  expect([hint('team-times'), hint('team-done_today')]).toEqual([
    'Median time from filing to each stage; this cycle is the last 7 days',
    'age: from filing to merge',
  ])
})

const shown = (svg: Element | null) =>
  draws(svg, Tick02Icon) ? 'check' : draws(svg, UserGroupIcon) ? 'people' : 'another icon'

test('an_empty_group_shows_a_check_only_where_nothing_is_wrong_and_no_summary_repeats_them', async () => {
  await mounted(() => answer(teamNow()))
  const empties = [...document.querySelectorAll('section [data-slot="empty"]')].map((p) => [
    p.querySelector('[data-slot="empty-title"]')?.textContent.trim(),
    shown(p.querySelector('svg')),
    p.querySelector('[data-slot="empty-description"]')?.textContent.trim(),
  ])
  expect(empties).toEqual([
    [
      'No ticket reached a stage today or this cycle.',
      'people',
      'Stage times appear here as tickets move through the workflow.',
    ],
    [
      'Nothing waits on you',
      'check',
      'Open questions and screenshots that need your approval appear here.',
    ],
    ['Nothing waits', 'check', 'Work waiting on review, checks, or a merge appears here.'],
    ['Nobody is working', 'people', 'Start an agent on a ticket and it works here.'],
    ['Nothing merged today', 'people', 'See Recently merged in Flow for earlier merges.'],
    ['Nothing is stale', 'check', 'Work that stops reporting progress appears here.'],
  ])
  expect(text()).not.toContain('Nobody is working and nothing waits.')
})

test('the_working_group_names_the_idle_and_paused_agents', async () => {
  await mounted(() => answer({ ...read(), idle: ['a', 'b'], paused: ['c'] }))
  expect(text()).toContain('Idle: a, b')
  expect(text()).toContain('Paused: c')
})

test('selecting_a_row_opens_its_peek_and_selecting_it_again_closes_it', async () => {
  await mounted(() => answer(withPeek()))
  expect(peekOpen()).toBe(false)
  rowButton('row-1').click()
  await flushPromises()
  expect(peekOpen()).toBe(true)
  expect(document.querySelector('#team-peek-title')?.textContent.trim()).toBe('Build the thing')
  expect(rowButton('row-1').getAttribute('aria-pressed')).toBe('true')
  rowButton('row-1').click()
  await flushPromises()

  expect(peekOpen()).toBe(false)
})

test('the_close_button_closes_the_peek_and_returns_focus_to_its_row', async () => {
  await mounted(() => answer(withPeek()))
  rowButton('row-1').click()
  await flushPromises()
  document.querySelector<HTMLElement>('aside button[aria-label="Close"]')?.click()
  await flushPromises()

  expect(peekOpen()).toBe(false)
  expect(document.activeElement).toBe(rowButton('row-1'))
})

test('escape_closes_the_peek_and_returns_focus_to_its_row', async () => {
  await mounted(() => answer(withPeek()))
  rowButton('row-1').click()
  await flushPromises()
  window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
  await flushPromises()

  expect(peekOpen()).toBe(false)
  expect(document.activeElement).toBe(rowButton('row-1'))
})

test('escape_typed_in_a_field_leaves_the_peek_open', async () => {
  await mounted(() => answer(withPeek()))
  rowButton('row-1').click()
  await flushPromises()
  const field = document.body.appendChild(document.createElement('input'))
  field.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
  await flushPromises()

  expect(peekOpen()).toBe(true)
})

test('escape_while_a_dialog_is_open_leaves_the_peek_open', async () => {
  await mounted(() => answer(withPeek()))
  rowButton('row-1').click()
  await flushPromises()
  const dialog = document.body.appendChild(document.createElement('div'))
  dialog.setAttribute('role', 'dialog')
  dialog.setAttribute('data-state', 'open')
  window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
  await flushPromises()

  expect(peekOpen()).toBe(true)
})

test('another_key_leaves_the_peek_open', async () => {
  await mounted(() => answer(withPeek()))
  rowButton('row-1').click()
  await flushPromises()
  window.dispatchEvent(new KeyboardEvent('keydown', { key: 'a' }))
  await flushPromises()

  expect(peekOpen()).toBe(true)
})

test('the_peek_stays_open_across_a_read', async () => {
  await mounted(() => answer(withPeek()))
  rowButton('row-1').click()
  await flushPromises()
  await tick()

  expect(peekOpen()).toBe(true)
})
