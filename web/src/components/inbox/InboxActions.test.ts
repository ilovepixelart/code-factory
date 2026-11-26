// @vitest-environment happy-dom
// An answer given in the Inbox is announced like every other page's change, and the keyboard
// follows the row that left (docs/ui.md: every change shows what it did).

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, test, vi } from 'vitest'
import { ATTENTION } from '../../lib/attention'
import { clear, notice } from '../../lib/notice'
import { SECTIONS, type Inbox, type InboxItem } from '../../lib/metrics'
import { memoryRouter } from '../../test/board'
import { present } from '../../test/present'
import InboxPage from '../../pages/InboxPage.vue'

const permission = (id: string): InboxItem => ({
  since: 1_790_000_000,
  kind: 'permission',
  reason: '',
  note: '',
  count: 1,
  images: [],
  ticket: { repository: 'sample', id: 'CF-1', title: 'First' },
  question: null,
  session: null,
  request: { id, tool: 'Bash', summary: `run ${id}` },
})

const listing = (items: InboxItem[]): Inbox => {
  const empty = Object.fromEntries(SECTIONS.map((s) => [s, [] as InboxItem[]]))
  return { ...empty, permissions: items, count: items.length, latest: '', next_up: null } as Inbox
}

const json = (body: unknown): Response =>
  new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })

/** The page over a server that lists `before` until `answered` is asked, `after` from then on. */
async function pageOver(before: InboxItem[], after: InboxItem[], answered: string) {
  let asked = false
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      if (url === answered) {
        asked = true
        return Promise.resolve(json({ notice: 'Allowed Bash on CF-1', undo: 'u1' }))
      }
      return Promise.resolve(json(listing(asked ? after : before)))
    }),
  )
  const page = mount(InboxPage, {
    attachTo: document.body,
    global: {
      provide: { [ATTENTION as symbol]: { refresh: () => Promise.resolve() } },
      plugins: [memoryRouter()],
      stubs: { RouterLink: true, teleport: true },
    },
  })
  await flushPromises()
  return page
}

async function allowRow(page: ReturnType<typeof mount>, n: number): Promise<void> {
  const allow = present(page.findAll('button').filter((b) => b.text() === 'Allow')[n], 'Allow')
  allow.element.focus()
  await allow.trigger('click')
  await flushPromises()
}

afterEach(() => {
  clear()
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

test('an_inbox_answer_shows_what_the_board_said_with_its_undo', async () => {
  const page = await pageOver([permission('r1')], [], '/api/permissions/r1/allow')

  await allowRow(page, 0)

  expect({ ...notice }).toEqual({
    text: 'Allowed Bash on CF-1',
    undo: 'u1',
    error: false,
    follow: null,
  })
})

test('focus_moves_to_the_row_that_takes_the_place_of_an_answered_one', async () => {
  const [first, second] = [permission('r1'), permission('r2')]
  const page = await pageOver([first, second], [second], '/api/permissions/r1/allow')

  await allowRow(page, 0)

  const rows = page.findAll(
    'section[aria-labelledby="inbox-permissions"] [data-slot="section-content"] > [data-slot="item-group"] > [role="listitem"]',
  )
  expect(rows).toHaveLength(1)
  expect(document.activeElement).toBe(rows[0]?.find('button').element)
})

test('focus_moves_to_the_section_heading_when_the_last_row_was_answered', async () => {
  const [first, second] = [permission('r1'), permission('r2')]
  const page = await pageOver([first, second], [first], '/api/permissions/r2/allow')

  await allowRow(page, 1)

  const heading = page.get('#inbox-permissions').element
  expect(document.activeElement).toBe(heading)
  expect(heading.getAttribute('tabindex')).toBe('-1')
})

test('focus_stays_on_the_page_when_the_answered_section_is_gone', async () => {
  const page = await pageOver([permission('r1')], [], '/api/permissions/r1/allow')

  await allowRow(page, 0)

  expect(document.activeElement).not.toBe(document.body)
  expect(page.find('#inbox-permissions').exists()).toBe(false)
})
