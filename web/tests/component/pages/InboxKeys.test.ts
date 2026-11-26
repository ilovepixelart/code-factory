// The Inbox from the keyboard and in a batch: j and k move between items, a number picks that
// choice of the focused question, a accepts its recommended one, y and n allow or deny a focused
// permission, Enter opens the item's ticket; "Accept N recommended" answers every question that
// recommends a choice, after a confirm that lists what is sent and says it cannot be taken back.

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, expect, test, vi } from 'vitest'
import { ATTENTION } from '@/lib/attention'
import { SECTIONS, type Inbox, type InboxItem } from '@/lib/metrics'
import { SHORTCUTS } from '@/lib/shortcuts'
import { memoryRouter } from '../../support/board'
import InboxPage from '@/pages/InboxPage.vue'

const choice = (text: string, recommended = false) => ({
  text,
  recommended,
  reason: '',
  ticked: false,
})
const base: InboxItem = {
  since: 1_790_000_000,
  kind: 'question',
  reason: '',
  note: '',
  count: 1,
  images: [],
  ticket: { repository: 'sample', id: 'CF-1', title: 'First' },
  question: null,
  session: null,
  request: null,
}
const expiry: InboxItem = {
  ...base,
  question: {
    document: 'spec',
    index: 0,
    text: 'Do gift cards expire?',
    several: false,
    choices: [choice('Never', true), choice('After five years')],
  },
}
const order: InboxItem = {
  ...base,
  ticket: { repository: 'sample', id: 'CF-2', title: 'Second' },
  question: {
    document: 'spec',
    index: 0,
    text: 'Which is spent first?',
    several: false,
    choices: [choice('The coupon'), choice('The card', true)],
  },
}
const open: InboxItem = {
  ...base,
  ticket: { repository: 'sample', id: 'CF-3', title: 'Third' },
  question: { document: 'spec', index: 0, text: 'Anything else?', several: false, choices: [] },
}
const permission: InboxItem = {
  ...base,
  kind: 'permission',
  ticket: { repository: 'sample', id: 'CF-4', title: 'Fourth' },
  request: { id: 'r1', tool: 'Bash', summary: 'ls' },
}

interface Posted {
  path: string
  body: unknown
}

let page: VueWrapper | null = null

async function shown(questions: InboxItem[], permissions: InboxItem[] = []) {
  const empty = Object.fromEntries(SECTIONS.map((s) => [s, [] as InboxItem[]]))
  const listed = { ...empty, questions, permissions, count: 1, latest: '', next_up: null } as Inbox
  const posted: Posted[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn((path: string, init?: RequestInit) => {
      if (init?.method === 'POST')
        posted.push({
          path,
          body: JSON.parse(typeof init.body === 'string' ? init.body : '{}') as unknown,
        })
      return Promise.resolve(
        new Response(JSON.stringify(init?.method === 'POST' ? {} : listed), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    }),
  )
  const router = memoryRouter()
  await router.push('/inbox')
  const header = document.createElement('div')
  header.id = 'header-controls'
  document.body.append(header)
  page = mount(InboxPage, {
    attachTo: document.body,
    global: {
      provide: { [ATTENTION as symbol]: { refresh: () => Promise.resolve() } },
      plugins: [router],
    },
  })
  await flushPromises()
  return { posted, router }
}

async function press(key: string): Promise<void> {
  window.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }))
  await flushPromises()
}

const focused = (): string =>
  document.activeElement?.closest('[data-inbox-item]')?.getAttribute('data-inbox-item') ?? ''

afterEach(() => {
  page?.unmount()
  page = null
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

test('j_and_k_move_the_focus_between_inbox_items', async () => {
  await shown([expiry, order], [permission])

  await press('j')
  const first = focused()
  await press('j')
  const second = focused()
  await press('j')
  const third = focused()
  await press('k')

  expect([first, second, third, focused()]).toEqual([
    'Do gift cards expire?',
    'Which is spent first?',
    'Allow Bash?',
    'Which is spent first?',
  ])
})

test('a_number_picks_that_choice_and_a_answers_with_the_pick_the_recommended_until_another', async () => {
  const { posted } = await shown([expiry, order])

  await press('j')
  await press('2')
  await press('a')
  await press('j')
  await press('a')

  expect(posted.map((p) => [p.path, (p.body as { choices?: string[] }).choices])).toEqual([
    ['/api/tickets/sample/CF-1/answers', ['After five years']],
    ['/api/tickets/sample/CF-2/answers', ['The card']],
  ])
})

test('y_and_n_allow_or_deny_the_focused_permission', async () => {
  const { posted } = await shown([], [permission])

  await press('j')
  await press('n')

  expect(posted.map((p) => p.path)).toEqual(['/api/permissions/r1/deny'])
})

test('keys_typed_into_a_field_are_not_inbox_keys', async () => {
  const { posted } = await shown([expiry])
  const field = document.querySelector<HTMLInputElement>('input[name="answer"]')

  field?.focus()
  field?.dispatchEvent(new KeyboardEvent('keydown', { key: 'a', bubbles: true }))
  await flushPromises()

  expect(posted).toEqual([])
})

test('enter_opens_the_focused_items_ticket', async () => {
  const { router } = await shown([expiry])

  await press('j')
  await press('Enter')

  expect(router.currentRoute.value.path).toBe('/tickets/sample/CF-1')
})

test('accept_recommended_lists_what_it_sends_and_answers_each_question', async () => {
  const { posted } = await shown([expiry, order, open])
  const accept = [...document.querySelectorAll('button')].find((b) =>
    b.textContent.trim().startsWith('Accept'),
  )

  accept?.click()
  await flushPromises()
  const dialog = document.querySelector('[role="alertdialog"]')?.textContent ?? ''
  const send = [...document.querySelectorAll('[role="alertdialog"] button')].find((b) =>
    b.textContent.includes('Send'),
  )
  send?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  await flushPromises()

  expect({
    button: accept?.textContent.trim(),
    lists: ['Do gift cards expire?', 'Never', 'Which is spent first?', 'The card'].every((t) =>
      dialog.includes(t),
    ),
    final: dialog.includes('cannot be undone'),
    sent: posted.map((p) => (p.body as { choices?: string[] }).choices),
  }).toEqual({
    button: 'Accept 2 recommended',
    lists: true,
    final: true,
    sent: [['Never'], ['The card']],
  })
})

test('the_shortcut_sheet_lists_the_inbox_keys', () => {
  const keys = SHORTCUTS.map((s) => s.keys.join(' '))

  expect(keys).toEqual(expect.arrayContaining(['j k', '1 … 9', 'a', 'y n', 'enter']))
})
