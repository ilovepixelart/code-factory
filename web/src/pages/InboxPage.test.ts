// @vitest-environment happy-dom
// CF-310: a permission answer disables both its buttons while it is pending, and its refusal
// shows, in the page's notice once the request has left (CF-434), named for its item (CF-435)
// (docs/ui.md: non-idempotent actions disable their control; every refusal shows).

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { ATTENTION } from '../lib/attention'
import { clear, notice } from '../lib/notice'
import { SECTIONS, type Inbox, type InboxItem, type Section } from '../lib/metrics'
import { memoryRouter } from '../test/board'
import { present } from '../test/present'
import InboxPage from './InboxPage.vue'

const request: InboxItem = {
  since: 1_790_000_000,
  kind: 'permission',
  reason: '',
  note: '',
  count: 1,
  images: [],
  ticket: { repository: 'sample', id: 'CF-1', title: 'First' },
  question: null,
  session: null,
  request: { id: 'r1', tool: 'Bash', summary: 'ls' },
}

function inbox(section: Section = 'permissions', item: InboxItem = request): Inbox {
  const empty = Object.fromEntries(SECTIONS.map((s) => [s, [] as InboxItem[]]))
  return { ...empty, [section]: [item], count: 1, latest: '', next_up: null } as Inbox
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** The inbox with nothing left in it, as a refresh reads it once its items are gone. */
function emptied(listed: Inbox): Inbox {
  const empty = Object.fromEntries(SECTIONS.map((s) => [s, [] as InboxItem[]]))
  return { ...listed, ...empty, count: 0, next_up: null }
}

/**
 * The page over a server whose answer to `path` waits until the returned function sends it; once
 * `path` is asked, the inbox reads as `after`.
 */
async function pageHolding(
  path: string,
  listed: Inbox = inbox(),
  after: Inbox = listed,
): Promise<{
  page: ReturnType<typeof mount>
  answer: (response: Response) => void
}> {
  let answer: (response: Response) => void = () => undefined
  const held = new Promise<Response>((resolve) => (answer = resolve))
  let asked = false
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      if (url !== path) return Promise.resolve(json(asked ? after : listed))
      asked = true
      return held
    }),
  )
  const page = mount(InboxPage, {
    global: {
      provide: { [ATTENTION as symbol]: { refresh: () => Promise.resolve() } },
      plugins: [memoryRouter()],
      stubs: { RouterLink: true, teleport: true },
    },
  })
  await flushPromises()
  return { page, answer }
}

function buttons(page: ReturnType<typeof mount>) {
  const named = (name: string) =>
    present(
      page.findAll('button').find((b) => b.text() === name),
      name,
    )
  return { allow: named('Allow'), deny: named('Deny') }
}

afterEach(() => {
  clear()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

test('an idle pull request links back to GitHub', async () => {
  const url = 'https://github.com/example/sample/pull/3'
  const { page } = await pageHolding(
    '',
    inbox('idle', { ...request, kind: 'idle', reason: url, request: null }),
  )

  const section = page.get('[aria-labelledby="inbox-idle"]')
  expect(section.text()).toContain('Idle pull requests')
  expect(section.get(`a[href="${url}"]`).text()).toBe('Open pull request')
})

describe('a permission request in the inbox', () => {
  test('a_pending_permission_answer_disables_both_buttons', async () => {
    const { page, answer } = await pageHolding('/api/permissions/r1/allow')

    await buttons(page).allow.trigger('click')
    const pending = buttons(page)

    expect(pending.allow.attributes('disabled')).toBeDefined()
    expect(pending.deny.attributes('disabled')).toBeDefined()
    answer(json({ notice: 'Allowed', undo: null }))
    await flushPromises()
    expect(buttons(page).allow.attributes('disabled')).toBeUndefined()
  })

  test('an_answered_request_that_leaves_puts_nothing_in_the_notice', async () => {
    const { page, answer } = await pageHolding(
      '/api/permissions/r1/allow',
      inbox(),
      emptied(inbox()),
    )

    await buttons(page).allow.trigger('click')
    answer(json({ notice: '', undo: null }))
    await flushPromises()

    expect(page.find('section[aria-labelledby="inbox-permissions"]').exists()).toBe(false)
    expect({ text: notice.text, error: notice.error }).toEqual({ text: '', error: false })
  })

  // CF-434: the refresh after the refusal no longer lists the request, as the board's does once
  // the agent stopped waiting.
  test('a_refused_permission_answer_shows_its_reason', async () => {
    const { page, answer } = await pageHolding(
      '/api/permissions/r1/deny',
      inbox(),
      emptied(inbox()),
    )

    await buttons(page).deny.trigger('click')
    answer(json({ detail: 'the request is no longer waiting' }, 409))
    await flushPromises()

    expect(page.find('section[aria-labelledby="inbox-permissions"]').exists()).toBe(false)
    expect({ text: notice.text, error: notice.error }).toEqual({
      text: 'CF-1 permission: the request is no longer waiting',
      error: true,
    })
  })
})

// CF-338: the inbox's answers and merges as docs/ui.md (The kanban, Frontend rules) sets them.
const question: InboxItem = {
  ...request,
  kind: 'question',
  request: null,
  question: { document: 'brd.md', index: 1, text: 'Which size?', choices: [], several: false },
}
const mergeable: InboxItem = {
  ...request,
  kind: 'mergeable',
  reason: 'https://github.com/o/r/pull/1',
  request: null,
}

describe('the inbox', () => {
  test('an_inbox_answer_being_typed_survives_a_refresh', async () => {
    vi.useFakeTimers()
    const { page } = await pageHolding('/api/none', inbox('questions', question))
    await page.get('input[aria-label="Answer to Which size?"]').setValue('large')

    await vi.advanceTimersByTimeAsync(5000)
    await flushPromises()

    const box = page.get<HTMLInputElement>('input[aria-label="Answer to Which size?"]')
    expect(vi.mocked(fetch).mock.calls.filter(([url]) => url === '/api/inbox')).toHaveLength(2)
    expect(box.element.value).toBe('large')
  })

  // How much the merge asks a reviewer to read (docs/ui.md, The kanban): Large past 400 lines.
  test('a_merge_shows_its_pull_requests_size_and_a_large_one_says_so', async () => {
    const size = { additions: 1240, deletions: 380, changed_files: 27 }
    const { page } = await pageHolding('/api/none', inbox('mergeable', { ...mergeable, size }))

    const shown = page
      .findAll('section[aria-labelledby="inbox-mergeable"] [data-pull-size] > *')
      .map((part) => part.text())

    expect(shown).toEqual(['+1,240 −380', 'Large'])
  })

  test('a_merge_github_refuses_shows_the_refusal_in_its_item', async () => {
    const { page, answer } = await pageHolding(
      '/api/tickets/sample/CF-1/merge',
      inbox('mergeable', mergeable),
    )
    const merge = () =>
      present(
        page.findAll('button').find((b) => b.text() === 'Merge'),
        'Merge',
      )

    await merge().trigger('click')
    const pending = merge().attributes('disabled')
    answer(json({ detail: 'GitHub refused the merge: the base branch policy prohibits it' }, 409))
    await flushPromises()

    expect(pending).toBeDefined()
    expect(
      page.get('section[aria-labelledby="inbox-mergeable"] [role="listitem"]').text(),
    ).toContain('GitHub refused the merge: the base branch policy prohibits it')
  })
})

// CF-350: a capture is sent back from its item with what should change, as mock.md draws it.
const screens: InboxItem = {
  ...request,
  kind: 'screens',
  reason: 'abc123',
  images: ['inbox-light.png'],
  request: null,
}

describe('screens to approve', () => {
  test('a_capture_is_sent_back_from_the_inbox_with_a_reason', async () => {
    const path = '/api/tickets/sample/CF-1/screens-changes'
    const answers: ((response: Response) => void)[] = []
    let listed = inbox('screens', screens)
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) =>
        url === path
          ? new Promise<Response>((resolve) => answers.push(resolve))
          : Promise.resolve(json(listed)),
      ),
    )
    // A click submits a form only while it is in the document.
    const page = mount(InboxPage, {
      attachTo: document.body,
      global: {
        provide: { [ATTENTION as symbol]: { refresh: () => Promise.resolve() } },
        plugins: [memoryRouter()],
        stubs: { RouterLink: true, teleport: true },
      },
    })
    await flushPromises()
    const named = (name: string) =>
      present(
        page.findAll('button').find((b) => b.text() === name),
        name,
      )
    const item = () => page.get('section[aria-labelledby="inbox-screens"] [role="listitem"]')
    const reason = 'The dark theme footer is darker than the page'

    expect(page.find('textarea').exists()).toBe(false)
    await named('Request changes').trigger('click')
    const box = page.get('textarea')
    const label = page.get(`label[for="${String(box.attributes('id'))}"]`)
    const empty = named('Send back').attributes('disabled')
    await box.setValue('   ')
    const blank = named('Send back').attributes('disabled')
    await box.setValue(reason)
    const ready = named('Send back').attributes('disabled')
    await named('Send back').trigger('click')
    const sending = named('Send back').attributes('disabled')
    present(
      answers[0],
      'the first request',
    )(json({ detail: 'no capture of the current tree waits' }, 409))
    await flushPromises()
    const refusal = item().text()
    await named('Send back').trigger('click')
    listed = { ...listed, screens: [], count: 0 }
    present(
      answers[1],
      'the second request',
    )(json({ notice: 'Sent the screens of CF-1 back', undo: null }))
    await flushPromises()
    const sent = vi
      .mocked(fetch)
      .mock.calls.filter(([url]) => url === path)
      .map(([, init]) =>
        typeof init?.body === 'string' ? (JSON.parse(init.body) as unknown) : null,
      )

    expect(label.text()).toBe('What should change?')
    expect(empty).toBeDefined()
    expect(blank).toBeDefined()
    expect(ready).toBeUndefined()
    expect(sending).toBeDefined()
    expect(refusal).toContain('no capture of the current tree waits')
    expect(sent).toEqual([{ reason }, { reason }])
    expect(page.find('section[aria-labelledby="inbox-screens"]').exists()).toBe(false)
    page.unmount()
  })

  test('request_changes_focuses_its_reason_and_cancel_returns_to_the_button', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(json(inbox('screens', screens)))),
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
    const named = (name: string) =>
      present(
        page.findAll('button').find((b) => b.text() === name),
        name,
      )
    const opener = named('Request changes')

    await opener.trigger('click')
    await flushPromises()
    const typing = document.activeElement
    const reason = page.get('textarea').element
    await named('Cancel').trigger('click')
    await flushPromises()

    expect(typing).toBe(reason)
    expect(page.find('textarea').exists()).toBe(false)
    expect(document.activeElement).toBe(opener.element)
    page.unmount()
  })

  test('approve_shows_a_spinner_while_it_is_sent_and_request_changes_does_not', async () => {
    const path = '/api/tickets/sample/CF-1/screens-approval'
    const answers: ((response: Response) => void)[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) =>
        url === path
          ? new Promise<Response>((resolve) => answers.push(resolve))
          : Promise.resolve(json(inbox('screens', screens))),
      ),
    )
    const page = mount(InboxPage, {
      global: {
        provide: { [ATTENTION as symbol]: { refresh: () => Promise.resolve() } },
        plugins: [memoryRouter()],
        stubs: { RouterLink: true, teleport: true },
      },
    })
    await flushPromises()
    const named = (name: string) =>
      present(
        page.findAll('button').find((b) => b.text() === name),
        name,
      )
    const spinning = (name: string) => named(name).find('[role="status"]').exists()

    await named('Approve').trigger('click')
    const sending = [spinning('Approve'), spinning('Request changes')]
    present(answers[0], 'the approval')(json({ notice: 'Approved', undo: null }))
    await flushPromises()

    expect(sending).toEqual([true, false])
    expect(page.find('section[aria-labelledby="inbox-screens"] [role="status"]').exists()).toBe(
      false,
    )
    page.unmount()
  })

  test('each_capture_image_is_an_attachment_that_opens_the_full_image', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(json(inbox('screens', screens)))),
    )
    const page = mount(InboxPage, {
      global: {
        provide: { [ATTENTION as symbol]: { refresh: () => Promise.resolve() } },
        plugins: [memoryRouter()],
        stubs: { RouterLink: true, teleport: true },
      },
    })
    await flushPromises()
    const attachment = page.get('section[aria-labelledby="inbox-screens"] [data-slot="attachment"]')
    const open = attachment.get('[data-slot="attachment-trigger"]')

    expect(attachment.get('[data-slot="attachment-title"]').text()).toBe('inbox light')
    expect(attachment.get('[data-slot="attachment-description"]').text()).toBe('tree abc123')
    expect([open.attributes('href'), open.attributes('aria-label')]).toEqual([
      '/api/captures/sample/CF-1/abc123/inbox-light.png',
      'Open inbox light',
    ])
    page.unmount()
  })
})

// CF-331: a question's choices are answered from its item, as mock.md draws it.
const choice = (text: string) => ({ text, recommended: false, reason: '', ticked: false })
const summary: InboxItem = {
  ...question,
  question: {
    document: 'uat.md',
    index: 0,
    text: 'Which page should the summary open on?',
    several: false,
    choices: [
      { ...choice('Flow'), recommended: true, reason: 'it already holds the weekly numbers' },
      choice('Tickets'),
    ],
  },
}
const notices: InboxItem = {
  ...question,
  question: {
    document: 'uat.md',
    index: 1,
    text: 'Which notices should a run send?',
    several: true,
    choices: [
      choice('When it ends'),
      choice('When it asks a question'),
      choice('When its checks fail'),
    ],
  },
}
const empty: InboxItem = {
  ...question,
  question: {
    document: 'uat.md',
    index: 2,
    text: 'What should the empty state say?',
    several: false,
    choices: [],
  },
}

describe('a question with choices', () => {
  test('a_question_s_choices_are_answered_from_the_inbox', async () => {
    vi.useFakeTimers()
    const path = '/api/tickets/sample/CF-1/answers'
    const replies: ((response: Response) => void)[] = []
    const listed = { ...inbox(), questions: [summary, notices, empty], count: 3 }
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) =>
        url === path
          ? new Promise<Response>((resolve) => replies.push(resolve))
          : Promise.resolve(json(listed)),
      ),
    )
    // A click submits a form only while it is in the document.
    const page = mount(InboxPage, {
      attachTo: document.body,
      global: {
        provide: { [ATTENTION as symbol]: { refresh: () => Promise.resolve() } },
        plugins: [memoryRouter()],
        stubs: { RouterLink: true, teleport: true },
      },
    })
    await flushPromises()
    const item = (n: number) =>
      page.findAll('section[aria-labelledby="inbox-questions"] article')[n]
    const one = () => present(item(0), 'the one question')
    const several = () => present(item(1), 'the several question')
    const free = present(item(2), 'the free question')
    const press = (li: ReturnType<typeof one>, name: string) =>
      present(
        li.findAll('button').find((b) => b.text() === name),
        name,
      )
    const boxes = () => several().findAll('[role="checkbox"]')
    const other = 'input[aria-label="Other answer to Which page should the summary open on?"]'

    const radios = () => one().findAll('[role="radio"]')
    const shown = {
      oneButtons: one()
        .findAll('button:not([role])')
        .map((b) => b.text()),
      oneRadios: radios().length,
      oneStarts: radios().map((r) => r.attributes('aria-checked') === 'true'),
      oneReason: one().text().includes('it already holds the weekly numbers'),
      severalButtons: several()
        .findAll('button:not([role])')
        .map((b) => b.text()),
      checkboxes: boxes().length,
      picks: [one().text().includes('Pick one'), several().text().includes('Pick any')],
      freeBox: free.find('input[aria-label="Answer to What should the empty state say?"]').exists(),
      freeChoices: free.findAll('[role="radio"], [role="checkbox"]').length,
    }
    const idle = press(several(), 'Answer').attributes('disabled')
    await present(boxes()[1], 'a choice').trigger('click')
    await present(boxes()[2], 'a choice').trigger('click')
    await vi.advanceTimersByTimeAsync(5000)
    await flushPromises()
    const kept = boxes().map((b) => b.attributes('aria-checked') === 'true')
    const picked = press(several(), 'Answer with 2').attributes('disabled')
    await press(several(), 'Answer with 2').trigger('click')
    present(replies[0], 'the first answer')(json({ notice: 'Answered', undo: null }))
    await flushPromises()
    const ready = press(one(), 'Answer').attributes('disabled')
    await one().get(other).setValue('The inbox')
    await press(one(), 'Answer').trigger('click')
    present(replies[1], 'the second answer')(json({ detail: 'no question 0 in uat.md' }, 404))
    await flushPromises()
    const refusal = one().text()
    await present(radios()[1], 'Tickets').trigger('click')
    await press(one(), 'Answer').trigger('click')
    const sent = vi
      .mocked(fetch)
      .mock.calls.filter(([url]) => url === path)
      .map(([, init]) =>
        typeof init?.body === 'string' ? (JSON.parse(init.body) as unknown) : null,
      )

    expect(shown).toEqual({
      oneButtons: ['Answer'],
      oneRadios: 3,
      oneStarts: [true, false, false],
      oneReason: true,
      severalButtons: ['Select all', 'Answer'],
      checkboxes: 4,
      picks: [true, true],
      freeBox: true,
      freeChoices: 0,
    })
    expect(idle).toBeDefined()
    expect(kept).toEqual([false, true, true, false])
    expect(picked).toBeUndefined()
    expect(ready).toBeUndefined()
    expect(sent).toEqual([
      {
        document: 'uat.md',
        index: 1,
        question: 'Which notices should a run send?',
        choices: ['When it asks a question', 'When its checks fail'],
      },
      {
        document: 'uat.md',
        index: 0,
        question: 'Which page should the summary open on?',
        answer: 'The inbox',
      },
      {
        document: 'uat.md',
        index: 0,
        question: 'Which page should the summary open on?',
        choices: ['Tickets'],
      },
    ])
    expect(refusal).toContain('no question 0 in uat.md')
    page.unmount()
  })

  // The recommended choice is marked on its own card, starts picked, and its reason is the line
  // under its label; the line under the question says which document asked it.
  test('the_recommended_choice_is_marked_on_its_card_starts_picked_and_says_why', async () => {
    const listed = { ...inbox(), questions: [summary], count: 1 }
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(json(listed))),
    )
    const page = mount(InboxPage, {
      global: {
        provide: { [ATTENTION as symbol]: { refresh: () => Promise.resolve() } },
        plugins: [memoryRouter()],
        stubs: { RouterLink: true, teleport: true },
      },
    })
    await flushPromises()
    const asked = page.get('section[aria-labelledby="inbox-questions"] article')
    const card = present(
      asked.findAll('[data-slot="field-label"]').find((c) => c.find('[data-recommended]').exists()),
      'the recommended card',
    )

    expect({
      label: card.text().replace(/\s+/g, ' ').trim(),
      picked: card.get('[data-recommended]').attributes('aria-checked'),
      badges: asked.findAll('[data-slot="badge"]').map((b) => b.text()),
      asked: asked.text().includes('Asked in uat.md'),
    }).toEqual({
      label: 'Flow Recommended it already holds the weekly numbers',
      picked: 'true',
      badges: ['Recommended'],
      asked: true,
    })
    page.unmount()
  })

  // An answer is read in full: the choices stack as cards whose words wrap, never a strip that
  // scrolls sideways behind a fade, where the last one was cut off.
  test('the_choices_of_a_question_stack_as_cards_whose_words_wrap', async () => {
    const listed = { ...inbox(), questions: [summary], count: 1 }
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(json(listed))),
    )
    const page = mount(InboxPage, {
      global: {
        provide: { [ATTENTION as symbol]: { refresh: () => Promise.resolve() } },
        plugins: [memoryRouter()],
        stubs: { RouterLink: true, teleport: true },
      },
    })
    await flushPromises()
    const asked = page.get('section[aria-labelledby="inbox-questions"] article')
    const group = asked.get('[role="radiogroup"]').classes()
    const words = asked.findAll('[data-slot="field-label"] .wrap-anywhere').length

    expect({ scrolls: group.includes('overflow-x-auto'), wrapping: words >= 2 }).toEqual({
      scrolls: false,
      wrapping: true,
    })
    page.unmount()
  })
})

describe('sending an answer', () => {
  // An action that is not idempotent sends once (docs/ui.md): a second Enter before the first answer
  // has landed sends nothing, as the question's busy state holds from the first.
  test('two_quick_enters_send_one_answer', async () => {
    const listed = { ...inbox(), questions: [summary], count: 1 }
    const posts: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string, init?: RequestInit) => {
        if (init?.method === 'POST') posts.push(url)
        return Promise.resolve(json(init?.method === 'POST' ? {} : listed))
      }),
    )
    const page = mount(InboxPage, {
      global: {
        provide: { [ATTENTION as symbol]: { refresh: () => Promise.resolve() } },
        plugins: [memoryRouter()],
        stubs: { RouterLink: true, teleport: true },
      },
    })
    await flushPromises()
    const box = page.get(
      'input[aria-label="Other answer to Which page should the summary open on?"]',
    )
    await box.setValue('Both')
    const typed = present(box.element.closest('form'), 'the answer form')

    typed.dispatchEvent(new Event('submit'))
    typed.dispatchEvent(new Event('submit'))
    await flushPromises()

    expect(posts.filter((url) => url.endsWith('/answers'))).toHaveLength(1)
    page.unmount()
  })
})

describe('the questions of one ticket', () => {
  const other: InboxItem = {
    ...question,
    ticket: { repository: 'sample', id: 'CF-2', title: 'Second' },
    since: 1_790_000_100,
    question: { document: 'brd.md', index: 0, text: 'Which colour?', choices: [], several: false },
  }

  test('three_questions_of_one_ticket_are_one_card_with_its_ticket_once', async () => {
    const listed = { ...inbox(), questions: [summary, other, notices, empty], count: 4 }
    const { page } = await pageHolding('/never', listed)

    const cards = page.findAll(
      'section[aria-labelledby="inbox-questions"] [data-slot="section-content"] > [data-slot="item-group"] > [role="listitem"]',
    )
    const first = present(cards[0], 'the CF-1 card')

    expect(cards).toHaveLength(2)
    expect(first.findAll('article').map((a) => a.get('p').text().replace(/\s+/g, ' '))).toEqual([
      'Which page should the summary open on? Pick one',
      'Which notices should a run send? Pick any',
      'What should the empty state say?',
    ])
    expect(first.findAll('router-link-stub').map((link) => link.attributes('to'))).toEqual([
      '/tickets/sample/CF-1',
    ])
    expect(present(cards[1], 'the CF-2 card').findAll('article')).toHaveLength(1)
    expect(page.get('section[aria-labelledby="inbox-questions"] h2').text()).toContain('4')
  })
})

// CF-434: every Inbox action's refusal shows, under its item while the item is listed, else in
// the page's notice.
interface Action {
  name: string
  section: Section
  item: InboxItem
  path: string
  button: string
  prepare?: (page: ReturnType<typeof mount>) => Promise<void>
}

const ticketPath = '/api/tickets/sample/CF-1'
const named = (page: ReturnType<typeof mount>, name: string) =>
  present(
    page.findAll('button').find((b) => b.text() === name),
    name,
  )
const actions: Action[] = [
  {
    name: 'Answer',
    section: 'questions',
    item: question,
    path: `${ticketPath}/answers`,
    button: 'Answer',
    prepare: (page) => page.get('input[name="answer"]').setValue('large'),
  },
  {
    name: 'Allow',
    section: 'permissions',
    item: request,
    path: '/api/permissions/r1/allow',
    button: 'Allow',
  },
  {
    name: 'Deny',
    section: 'permissions',
    item: request,
    path: '/api/permissions/r1/deny',
    button: 'Deny',
  },
  {
    name: 'Always allow',
    section: 'rules',
    item: {
      ...request,
      kind: 'rule',
      reason: 'Bash npm test',
      count: 3,
      request: null,
      ticket: null,
    },
    path: '/api/permissions/rules',
    button: 'Always allow',
  },
  {
    name: 'Restart agent',
    section: 'stopped',
    item: { ...request, kind: 'stopped', reason: 'exited 1', request: null },
    path: `${ticketPath}/runs`,
    button: 'Restart agent',
  },
  {
    name: 'Approve screens',
    section: 'screens',
    item: screens,
    path: `${ticketPath}/screens-approval`,
    button: 'Approve',
  },
  {
    name: 'Send back',
    section: 'screens',
    item: screens,
    path: `${ticketPath}/screens-changes`,
    button: 'Send back',
    prepare: async (page) => {
      await named(page, 'Request changes').trigger('click')
      await page.get('textarea').setValue('Too dark')
    },
  },
  {
    name: 'Merge',
    section: 'mergeable',
    item: mergeable,
    path: `${ticketPath}/merge`,
    button: 'Merge',
  },
]

/**
 * Refuse `action` with `refused: <name>`, the refresh after it listing its item again or not;
 * whether each row of its section holds the reason, and the page's notice.
 */
async function refuse(action: Action, stays: boolean) {
  const listed = inbox(action.section, action.item)
  let refused = false
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      if (url !== action.path)
        return Promise.resolve(json(refused && !stays ? emptied(listed) : listed))
      refused = true
      return Promise.resolve(json({ detail: `refused: ${action.name}` }, 409))
    }),
  )
  // A click submits a form only while it is in the document.
  const page = mount(InboxPage, {
    attachTo: document.body,
    global: {
      provide: { [ATTENTION as symbol]: { refresh: () => Promise.resolve() } },
      plugins: [memoryRouter()],
      stubs: { RouterLink: true, teleport: true },
    },
  })
  await flushPromises()
  await action.prepare?.(page)
  await named(page, action.button).trigger('click')
  await flushPromises()
  const rows = page
    .findAll(`section[aria-labelledby="inbox-${action.section}"] [role="listitem"]`)
    .map((li) => li.text().includes(`refused: ${action.name}`))
  const shown = { rows, notice: { text: notice.text, error: notice.error } }
  page.unmount()
  clear()
  return shown
}

// CF-435: the item each action's notice names, as the FRD lists them.
const ITEM_NAMES: Record<string, string> = {
  Answer: 'CF-1 question',
  Allow: 'CF-1 permission',
  Deny: 'CF-1 permission',
  'Always allow': 'Rule Bash npm test',
  'Restart agent': 'CF-1 stopped agent',
  'Approve screens': 'CF-1 screens',
  'Send back': 'CF-1 screens',
  Merge: 'CF-1 pull request',
}
const namedRefusal = (a: Action): string => `${String(ITEM_NAMES[a.name])}: refused: ${a.name}`

describe('a refused inbox action', () => {
  test('every_inbox_refusal_shows_after_its_item_leaves', async () => {
    const shown: Record<string, unknown> = {}
    for (const action of actions) shown[action.name] = await refuse(action, false)

    expect(shown).toEqual(
      Object.fromEntries(
        actions.map((a) => [a.name, { rows: [], notice: { text: namedRefusal(a), error: true } }]),
      ),
    )
  })

  test('a_refusal_notice_names_its_item', async () => {
    const shown: Record<string, string> = {}
    for (const action of actions) shown[action.name] = (await refuse(action, false)).notice.text

    expect(shown).toEqual(Object.fromEntries(actions.map((a) => [a.name, namedRefusal(a)])))
  })

  test('every_inbox_refusal_on_a_listed_item_shows_under_it_only', async () => {
    const shown: Record<string, unknown> = {}
    for (const action of actions) shown[action.name] = await refuse(action, true)

    expect(shown).toEqual(
      Object.fromEntries(
        actions.map((a) => [a.name, { rows: [true], notice: { text: '', error: false } }]),
      ),
    )
  })
})

// CF-435: the empty state and the rule's sentence.
const rule: InboxItem = {
  ...request,
  kind: 'rule',
  reason: 'Bash uv run pytest',
  count: 5,
  request: null,
  ticket: null,
}

describe('what the inbox says', () => {
  test('nothing_waits_on_you_shows_only_when_every_section_is_empty', async () => {
    const review: InboxItem = { ...request, kind: '', request: null }
    const shown: boolean[] = []
    for (const listed of [
      { ...inbox('rules', rule), count: 0 },
      { ...inbox('reviews', review), count: 0 },
      emptied(inbox()),
    ]) {
      const { page } = await pageHolding('/never', listed)
      shown.push(page.text().includes('Nothing needs you'))
      page.unmount()
    }

    expect(shown).toEqual([false, false, true])
  })

  // The owner: the empty Inbox says so inside a section Card, like every other page's empty state.
  test('nothing_waits_on_you_sits_in_a_section_card', async () => {
    const { page } = await pageHolding('/never', emptied(inbox()))
    const empty = page.get('[data-section] [data-slot="empty"]')

    expect([
      empty.get('[data-slot="empty-title"]').text(),
      empty.get('[data-slot="empty-description"]').text(),
    ]).toStrictEqual([
      'Nothing needs you',
      'Agents ask here when they need you: questions, permissions, reviews and merges.',
    ])
    page.unmount()
  })

  // CF-1178-R3: a refused first read shows the board's reason with Read again, never a blank page,
  // and the first read on its way says so.
  test('the_inbox_shows_a_refused_read', async () => {
    const { page, answer } = await pageHolding('/api/inbox')
    const reading = page.find('[aria-live="polite"]')
    const readingText = reading.exists() ? reading.text() : ''

    answer(json({ detail: 'the ledger could not be read' }, 500))
    await flushPromises()

    expect(readingText).toBe('Reading the inbox')
    expect(page.get('[role="alert"]').text()).toBe('the ledger could not be read Read again')
  })

  test('a_rule_says_how_often_it_was_allowed_once', async () => {
    const { page } = await pageHolding('/never', { ...inbox('rules', rule), count: 0 })

    const sentence = page
      .get('section[aria-labelledby="inbox-rules"] [role="listitem"] [data-slot="item-title"]')
      .text()

    expect(sentence.replace(/\s+/g, ' ')).toBe('You allowed Bash uv run pytest all 5 times')
  })
})

describe('pushing the inbox', () => {
  const failing = { host: 'ntfy.sh', failure: { at: 1_790_000_000, problem: 'HTTP 500' } }

  test('a_failing_push_says_where_why_and_that_it_is_tried_again', async () => {
    const at = new Date(1_790_000_000 * 1000).toLocaleTimeString('en-GB', { hour12: false })
    const { page } = await pageHolding('/never', { ...inbox(), push: failing })
    const notice = present(
      page.findAll('[aria-labelledby="push-failure-heading"]').at(0),
      'the push notice',
    )

    expect(notice.text().replace(/\s+/g, ' ')).toBe(
      `Push notifications fail Sending to ntfy.sh failed at ${at}: HTTP 500. What waits is sent again on the next try.`,
    )
    expect(page.text()).toContain('Push to ntfy.sh')
  })

  test('a_working_push_names_its_host_without_a_notice', async () => {
    const { page } = await pageHolding('/never', {
      ...inbox(),
      push: { host: 'ntfy.sh', failure: null },
    })

    expect(page.text()).toContain('Push to ntfy.sh')
    expect(page.text()).not.toContain('Push notifications fail')
  })

  test('an_unreadable_push_target_fails_without_a_host', async () => {
    const { page } = await pageHolding('/never', {
      ...inbox(),
      push: { host: '', failure: { at: 1_790_000_000, problem: 'push.json: no' } },
    })

    expect(page.text()).toContain('Sending failed at ')
    expect(page.text()).not.toContain('Push to')
  })
})

// CF-412: a ticket in Review with no recorded start shows no age; one with a start shows it.
describe('the review queue', () => {
  test('a_review_with_no_known_start_shows_no_age', async () => {
    vi.useFakeTimers({ now: new Date('2026-10-09T10:00:00Z') })
    const review = (id: string, title: string, since: number | null): InboxItem => ({
      ...request,
      kind: '',
      since,
      request: null,
      ticket: { repository: 'sample', id, title },
    })
    const reviews = [
      review('CF-9', 'New sidebar', null),
      review('CF-12', 'Audit log', Date.parse('2026-10-07T10:00:00Z') / 1000),
    ]
    const { page } = await pageHolding('/api/none', { ...inbox(), permissions: [], reviews })

    const rows = page.findAll('section[aria-labelledby="inbox-reviews"] [role="listitem"]')

    // The stubbed links render no text: what each row shows is its age alone.
    expect(rows.map((r) => r.text())).toEqual(['', '2d'])
    expect(rows[0]?.find('[title]').exists()).toBe(false)
    expect(rows[1]?.find('[title^="Waiting since"]').exists()).toBe(true)
  })
})

// CF-1213: a pull request whose fix rounds ran out says under its row what the rounds left; a row
// with rounds left says nothing.
describe('a pull request that waits on the owner', () => {
  test('a_row_whose_rounds_ran_out_says_what_they_left', async () => {
    const waits = (id: string, kind: string, note: string): InboxItem => ({
      ...request,
      kind,
      note,
      reason: `https://github.com/o/r/pull/${id.slice(3)}`,
      request: null,
      ticket: { repository: 'sample', id, title: 'Work' },
    })
    const stuck = 'Fixes stopped after 3 rounds: a review still requests changes'
    const failing = [waits('CF-1', 'failing', ''), waits('CF-2', 'stuck', stuck)]
    const { page } = await pageHolding('/never', { ...inbox(), permissions: [], failing })

    const rows = page.findAll('section[aria-labelledby="inbox-failing"] [role="listitem"]')

    expect(rows.map((row) => row.findAll('p').map((p) => p.text()))).toEqual([[], [stuck]])
    expect(rows.map((row) => row.find('a').attributes('href'))).toEqual([
      'https://github.com/o/r/pull/1',
      'https://github.com/o/r/pull/2',
    ])
    page.unmount()
  })
})

// CF-441: what the Inbox sends to restart an agent, and where a waiting session leads.
describe('restarting and opening', () => {
  test('a_restart_asks_for_accept_edits_and_a_loop', async () => {
    const stopped = { ...request, kind: 'stopped', reason: 'exited 1', request: null }
    const sent: { url: string; body: unknown }[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string, init?: RequestInit) => {
        if (init?.method === 'POST') {
          sent.push({ url, body: JSON.parse(init.body as string) as unknown })
          return Promise.resolve(json({ notice: 'Started', undo: null }, 201))
        }
        return Promise.resolve(json(inbox('stopped', stopped)))
      }),
    )
    const page = mount(InboxPage, {
      global: {
        provide: { [ATTENTION as symbol]: { refresh: () => Promise.resolve() } },
        plugins: [memoryRouter()],
        stubs: { RouterLink: true, teleport: true },
      },
    })
    await flushPromises()

    const restart = page.findAll('button').find((b) => b.text().includes('Restart agent'))
    await restart?.trigger('click')
    await flushPromises()

    expect(sent).toStrictEqual([
      {
        url: '/api/tickets/sample/CF-1/runs',
        body: { permissions: 'bypassPermissions', loop: true },
      },
    ])
    page.unmount()
  })

  test('a_waiting_session_links_to_its_page', async () => {
    const waiting = {
      ...request,
      kind: '',
      ticket: null,
      request: null,
      session: { session_id: 's-1', cwd: '/work/alpha', action: null },
    }
    const { page } = await pageHolding('/never', inbox('sessions', waiting))

    const targets = page.findAll('router-link-stub').map((link) => link.attributes('to'))

    expect(targets).toContain('/sessions/s-1')
    page.unmount()
  })
})

// CF-761-R2: each row a push announces carries the id its link names, so the
// scroll of CF-627-R2 reaches it; the ids are the server's, written out by hand.
describe('the rows a push names', () => {
  test('each_row_carries_the_id_its_push_names', async () => {
    const onTicket = { ...request, kind: '', request: null, reason: 'r' }
    const waiting = {
      ...onTicket,
      ticket: null,
      session: { session_id: 's-1', cwd: '/work/alpha', action: null },
    }
    const every = {
      ...inbox(),
      permissions: [],
      sessions: [waiting],
      stopped: [onTicket],
      screens: [onTicket],
      mergeable: [onTicket],
      failing: [onTicket],
    } as Inbox
    const { page } = await pageHolding('/never', every)

    const ids = [
      'sessions-s-1',
      'stopped-sample-CF-1',
      'screens-sample-CF-1',
      'mergeable-sample-CF-1',
      'failing-sample-CF-1',
    ]
    expect(ids.filter((id) => !page.find(`[role="listitem"][id="${id}"]`).exists())).toEqual([])
    page.unmount()
  })
})

// CF-627-R2: a push notification's link names its item after `#`; the page scrolls its own scroll
// area, the app's `[data-scroller]`, to put that item at its top, once, when the items first load, and leaves
// the scroll to the owner on later refreshes. Hand-worked: the item drawn 600 px down, the scroll
// area's top at 100 px, so the area scrolls by 500 px.
describe('opening the inbox from a push', () => {
  test('a_push_link_scrolls_its_item_into_view', async () => {
    vi.useFakeTimers()
    const both = { ...inbox(), questions: [question] } as Inbox
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(json(both))),
    )
    const target = 'question-sample-CF-1-brd.md-1'
    const drawn = vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (
      this: Element,
    ) {
      return new DOMRect(0, this.id === target ? 600 : 100, 390, 50)
    })
    const main = document.body.appendChild(document.createElement('div'))
    main.dataset.scroller = ''
    const router = memoryRouter()
    await router.push(`/inbox#${target}`)
    const page = mount(InboxPage, {
      attachTo: main.appendChild(document.createElement('div')),
      global: {
        provide: { [ATTENTION as symbol]: { refresh: () => Promise.resolve() } },
        plugins: [router],
        stubs: { RouterLink: true, teleport: true },
      },
    })
    try {
      await flushPromises()
      await vi.advanceTimersByTimeAsync(5000)
      await flushPromises()

      expect(main.scrollTop).toBe(500)
      expect(document.documentElement.scrollTop).toBe(0)
    } finally {
      page.unmount()
      main.remove()
      drawn.mockRestore()
    }
  })
})
