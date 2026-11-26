// CF-1428-R1: the coordinator's diagnoses are listed in the Inbox, each with its ticket and words.

import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { afterEach, expect, test, vi } from 'vitest'
import { ATTENTION } from '@/lib/attention'
import { SECTIONS, type Inbox, type InboxItem } from '@/lib/metrics'
import { memoryRouter } from '../../../support/board'
import InboxPage from '@/pages/InboxPage.vue'

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

const diagnosis = (id: string, text: string, since: number): InboxItem => ({
  since,
  kind: '',
  reason: '',
  note: '',
  count: 0,
  images: [],
  ticket: { repository: 'sample', id, title: `Ticket ${id}` },
  question: null,
  session: null,
  request: null,
  diagnosis: { author: 'coordinator', text },
})

async function pageOf(items: InboxItem[]) {
  const empty = Object.fromEntries(SECTIONS.map((s) => [s, [] as InboxItem[]]))
  const body = { ...empty, diagnoses: items, count: 0, latest: '', next_up: null } as Inbox
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } }),
      ),
    ),
  )
  const page = mount(InboxPage, {
    global: {
      provide: { [ATTENTION as symbol]: { refresh: () => Promise.resolve() } },
      plugins: [memoryRouter()],
      stubs: { RouterLink: RouterLinkStub, teleport: true },
    },
  })
  await flushPromises()
  return page
}

test('diagnoses_are_listed_with_their_ticket_and_text', async () => {
  const page = await pageOf([
    diagnosis('CF-2', 'Blocked by CF-1.', 1_790_000_200),
    diagnosis('CF-1', 'Idle for a week.', 1_790_000_100),
  ])

  const section = page.find('section[aria-labelledby="inbox-diagnoses"]')
  const rows = section.findAll('[role="listitem"]')

  expect(section.text()).toContain('Coordinator diagnoses')
  expect(rows).toHaveLength(2)
  expect(rows[0]?.text()).toContain('CF-2')
  expect(rows[0]?.text()).toContain('Blocked by CF-1.')
  expect(rows[1]?.text()).toContain('Idle for a week.')
  page.unmount()
})

test('no_diagnosis_draws_no_section', async () => {
  const page = await pageOf([])

  expect(page.find('#inbox-diagnoses').exists()).toBe(false)
  page.unmount()
})
