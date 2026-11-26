// @vitest-environment happy-dom

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { memoryRouter, provideBoard } from '../../test/board'
import { notice } from '../../lib/notice'
import { present } from '../../test/present'
import { BASE, view } from '../../test/ticketForm'
import TicketForm from '../TicketForm.vue'

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

const FINDINGS = [
  {
    id: 'F1',
    severity: 'high',
    file: 'src/api.rs',
    line: 42,
    text: 'The mock route follows a link out of mock/.',
    state: 'open',
    reason: '',
    by: '',
  },
  {
    id: 'F2',
    severity: 'low',
    file: 'web/x.vue',
    line: 7,
    text: 'A comment says too much.',
    state: 'dismissed',
    reason: 'intended wording',
    by: 'owner',
  },
]

/** The form over a server listing `findings` and answering each close with `closed`. */
async function withFindings(
  findings: unknown[],
  closed: () => Promise<Response> = () => new Promise<Response>(() => undefined),
) {
  const posts: { url: string; body: unknown }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      if ((init?.method ?? 'GET') !== 'GET') {
        posts.push({ url, body: typeof init?.body === 'string' ? JSON.parse(init.body) : null })
        return closed()
      }
      const body = url.endsWith('/findings') ? { findings } : view
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }))
    }),
  )
  // A fresh element per form: emptying the body would pull the portal anchors of a form mounted
  // earlier in the test out from under it.
  const app = document.body.appendChild(document.createElement('div'))
  const page = mount(TicketForm, {
    attachTo: app,
    props: { repository: 'sample', id: 'CF-1', page: true },
    global: {
      plugins: [memoryRouter([{ path: '/', component: { template: '<div />' } }])],
      provide: provideBoard(),
      stubs: { RouterLink: true, TicketChanges: true },
    },
  })
  await flushPromises()
  return { page, posts }
}

describe('review findings', () => {
  // CF-745-R1
  test('the_ticket_lists_its_review_findings', async () => {
    const { page } = await withFindings(FINDINGS)
    const rows = page.findAll('[aria-label="Review findings"] > li').map((li) => li.text())
    const none = await withFindings([])

    expect(rows).toHaveLength(2)
    expect(rows[0]).toContain('F1')
    expect(rows[0]).toContain('high')
    expect(rows[0]).toContain('src/api.rs:42')
    expect(rows[0]).toContain('The mock route follows a link out of mock/.')
    expect(rows[0]).toContain('open')
    expect(rows[1]).toContain('dismissed: intended wording (owner)')
    expect(none.page.find('[aria-label="Review findings"]').exists()).toBe(false)
    page.unmount()
    none.page.unmount()
  })

  // CF-745-R2
  test('an_open_finding_closes_with_a_reason', async () => {
    const { page, posts } = await withFindings(FINDINGS)
    const buttons = () => page.findAll('[aria-label="Review findings"] button')
    const box = page.find('input[aria-label="Reason for F1"]')
    expect([box.exists(), buttons().map((b) => b.text())]).toEqual([true, ['Fixed', 'Dismiss']])
    const button = (name: string) =>
      present(
        buttons().find((b) => b.text() === name),
        name,
      )
    await box.setValue('guarded now')

    await button('Fixed').trigger('click')
    await flushPromises()

    expect(posts).toEqual([
      { url: `${BASE}/findings/F1`, body: { state: 'fixed', reason: 'guarded now' } },
    ])
    expect([
      button('Fixed').attributes('disabled'),
      button('Dismiss').attributes('disabled'),
    ]).toEqual(['', ''])
    expect(page.findAll('input[aria-label^="Reason for"]')).toHaveLength(1)
    page.unmount()
  })

  // CF-745-R3
  test('a_refused_close_is_shown', async () => {
    const { page } = await withFindings(FINDINGS, () =>
      Promise.resolve(
        new Response(JSON.stringify({ detail: 'a reason is required' }), { status: 400 }),
      ),
    )

    const dismiss = page
      .findAll('[aria-label="Review findings"] button')
      .find((b) => b.text() === 'Dismiss')
    expect(dismiss?.exists()).toBe(true)
    await dismiss?.trigger('click')
    await flushPromises()

    expect(notice.text).toBe('a reason is required')
    expect(page.find('input[aria-label="Reason for F1"]').exists()).toBe(true)
    page.unmount()
  })
})

// A review run files findings while the ticket is open: they are read again with the ticket's own
// poll, not only when the ticket is opened.
test('findings_are_read_again_with_the_tickets_poll', async () => {
  const progress = {
    tool_calls: 0,
    reads: 0,
    changes: 0,
    files: { count: 0, names: [] },
    tokens: 0,
    last_activity: 0,
  }
  const running = {
    ...(view as object),
    runs: [{ id: 'r1', stage: 'review', iteration: 1, loop: false, started_at: 0, progress }],
  }
  let filed: unknown[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      const body = url.endsWith('/findings') ? { findings: filed } : running
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }))
    }),
  )
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] })
  try {
    const app = document.body.appendChild(document.createElement('div'))
    const page = mount(TicketForm, {
      attachTo: app,
      props: { repository: 'sample', id: 'CF-1', page: true },
      global: {
        plugins: [memoryRouter([{ path: '/', component: { template: '<div />' } }])],
        provide: provideBoard(),
        stubs: { RouterLink: true, TicketChanges: true },
      },
    })
    await flushPromises()
    const before = page.findAll('[aria-label="Review findings"] > li').length
    filed = FINDINGS
    await vi.advanceTimersByTimeAsync(5000)
    await flushPromises()
    const after = page.findAll('[aria-label="Review findings"] > li').length
    page.unmount()

    expect([before, after]).toEqual([0, 2])
  } finally {
    vi.useRealTimers()
  }
})

// CF-745-R4
test('a_malformed_finding_id_offers_no_close', async () => {
  const forged = { ...FINDINGS[0], id: '../../archive' }
  const { page } = await withFindings([forged, FINDINGS[0]])

  const rows = page.findAll('[aria-label="Review findings"] > li')
  expect(rows.map((row) => row.findAll('button').length)).toEqual([0, 2])
  page.unmount()
})
