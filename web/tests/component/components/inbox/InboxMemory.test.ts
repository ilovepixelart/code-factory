// CF-1168: an agent's memory proposal waits in the Inbox with where it came from, and the owner
// approves, edits or dismisses it there; a running action disables its buttons and a refusal
// shows under its item (docs/ui.md).

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { ATTENTION } from '@/lib/attention'
import { clear } from '@/lib/notice'
import { SECTIONS, type Inbox, type InboxItem } from '@/lib/metrics'
import { memoryRouter } from '../../../support/board'
import { validated } from '../../../support/form'
import { present } from '../../../support/present'
import InboxPage from '@/pages/InboxPage.vue'

const proposal: InboxItem = {
  since: 1_790_000_000,
  kind: 'memory',
  reason: '',
  note: '',
  count: 0,
  images: [],
  ticket: null,
  question: null,
  session: null,
  request: null,
  memory: {
    repository: 'sample',
    id: '2026-09-20-measure-before-tuning',
    kind: 'rule',
    statement: 'Measure before tuning',
    why: 'A guess cost a day',
    source: 'agent',
    guard: '',
    scope: 'build',
  },
}

const base = '/api/memory/sample/2026-09-20-measure-before-tuning'

function listing(items: InboxItem[]): Inbox {
  const empty = Object.fromEntries(SECTIONS.map((s) => [s, [] as InboxItem[]]))
  return { ...empty, memory: items, count: 0, latest: '', next_up: null } as Inbox
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** The page over a server whose answer to a change of `path` waits until the returned function sends it. */
async function pageHolding(path: string) {
  let answer: (response: Response) => void = () => undefined
  const held = new Promise<Response>((resolve) => (answer = resolve))
  // Only the action is held: the page's own reads of the inbox go on answering.
  const fetched = vi.fn((url: string, init?: RequestInit) =>
    url === path && init?.method !== undefined ? held : Promise.resolve(json(listing([proposal]))),
  )
  vi.stubGlobal('fetch', fetched)
  const page = mount(InboxPage, {
    global: {
      provide: { [ATTENTION as symbol]: { refresh: () => Promise.resolve() } },
      plugins: [memoryRouter()],
      stubs: { RouterLink: true, teleport: true },
    },
  })
  await flushPromises()
  return { page, answer, fetched }
}

function button(page: ReturnType<typeof mount>, name: string) {
  return present(
    page.findAll('section[aria-labelledby="inbox-memory"] button').find((b) => b.text() === name),
    name,
  )
}

afterEach(() => {
  clear()
  vi.unstubAllGlobals()
})

describe('memory proposals in the inbox', () => {
  // CF-1168-R8
  test('the_inbox_lists_a_memory_proposal_with_its_source', async () => {
    const { page } = await pageHolding('/never')

    const section = page.get('section[aria-labelledby="inbox-memory"]')
    const facts = section
      .findAll(
        '[role="listitem"] [data-slot="badge"], [role="listitem"] .text-muted-foreground span',
      )
      .map((s) => s.text())

    expect(section.get('h2').text()).toContain('Memory proposals')
    expect(section.text()).toContain('Measure before tuning')
    expect(section.text()).toContain('Why: A guess cost a day')
    expect(facts).toEqual(['Rule', 'agent', 'sample'])
    expect(section.findAll('[role="listitem"] button').map((b) => b.text())).toEqual([
      'Approve',
      'Edit',
      'Dismiss',
    ])
  })

  // CF-1168-R8: Approve posts, both buttons wait while it runs, and its refusal shows under it.
  test('approving_disables_the_proposals_buttons_and_shows_a_refusal', async () => {
    const { page, answer, fetched } = await pageHolding(`${base}/approve`)

    await button(page, 'Approve').trigger('click')
    await flushPromises()
    const waiting = ['Approve', 'Dismiss'].map(
      (name) => button(page, name).attributes('disabled') !== undefined,
    )
    answer(json({ detail: 'it is not proposed' }, 400))
    await flushPromises()

    expect(waiting).toEqual([true, true])
    expect(
      fetched.mock.calls.some(
        ([url, init]) => url === `${base}/approve` && init?.method === 'POST',
      ),
    ).toBe(true)
    expect(
      page
        .get('section[aria-labelledby="inbox-memory"] [role="listitem"] [data-slot="field-error"]')
        .text(),
    ).toBe('it is not proposed')
  })

  // CF-1168-R8: Edit opens the entry's form and saves it with PATCH.
  test('editing_a_proposal_saves_its_fields', async () => {
    const { page, answer, fetched } = await pageHolding(base)

    await button(page, 'Edit').trigger('click')
    const form = page.get('section[aria-labelledby="inbox-memory"] form')
    expect(form.get('select').element.value).toBe('build')
    await form.get('textarea').setValue('Measure before tuning anything')
    await form.trigger('submit')
    await validated()
    answer(json({ notice: 'Saved', undo: 't' }))
    await flushPromises()

    const sent = present(
      fetched.mock.calls.find(([url, init]) => url === base && init?.method === 'PATCH'),
      'the PATCH',
    )
    expect(JSON.parse(sent[1]?.body as string)).toMatchObject({
      statement: 'Measure before tuning anything',
      source: 'agent',
      scope: 'build',
    })
  })
})
