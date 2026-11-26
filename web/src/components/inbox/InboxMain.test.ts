// @vitest-environment happy-dom
// CF-1251: a default branch whose own run failed leads the Inbox with the step that failed, the
// commit, the log and its last lines, and the merge the search named with a link to its ticket.

import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { ATTENTION } from '../../lib/attention'
import { SECTIONS, type Inbox, type InboxItem } from '../../lib/metrics'
import { memoryRouter } from '../../test/board'
import { present } from '../../test/present'
import InboxPage from '../../pages/InboxPage.vue'

const failing: InboxItem = {
  since: 1_790_000_000,
  kind: 'main',
  reason: '',
  note: '',
  count: 0,
  images: [],
  ticket: null,
  question: null,
  session: null,
  request: null,
  main: {
    repository: 'sample',
    commit: 'a5a09a9f49f600125854b489b1db17e39166c88d',
    step: 'rust-test',
    exit_code: 100,
    log: '/state/checks/sample-main-1790000000.log',
    tail: 'FAIL [ 0.1s] (3/9) code-factory::suite readme\ngate: rust-test failed (exit 100) after 61s',
    passed: 'ad896a31f0000000000000000000000000000000',
    broken_by: '',
    ticket: '',
  },
}

function listing(items: InboxItem[]): Inbox {
  const empty = Object.fromEntries(SECTIONS.map((s) => [s, [] as InboxItem[]]))
  return { ...empty, main: items, count: items.length, latest: '', next_up: null } as Inbox
}

async function pageOf(items: InboxItem[]) {
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify(listing(items)), {
          headers: { 'Content-Type': 'application/json' },
        }),
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

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('the Inbox when a default branch fails its own run', () => {
  test('shows the step, the commit, the log and its last lines', async () => {
    const page = await pageOf([failing])

    const row = page.get('#main-sample')
    expect(page.find('#inbox-main').text()).toBe('Failing main, 1')
    const trigger = row.get('[data-slot="trace-collapsible-trigger"]')
    expect(trigger.text()).toBe('sample: rust-test failed at a5a09a9f')
    expect(trigger.attributes('aria-expanded')).toBe('true')
    expect(row.text()).toContain('/state/checks/sample-main-1790000000.log')
    const lines = row.get('ol[aria-label="Last lines of the log"]').findAll('li')
    expect(lines.map((line) => line.text())).toEqual([
      'FAIL [ 0.1s] (3/9) code-factory::suite readme',
      'gate: rust-test failed (exit 100) after 61s',
    ])
    expect(row.text()).not.toContain('Broken by')
    expect(row.findComponent(RouterLinkStub).exists()).toBe(false)
  })

  test('names the merge that broke it and links to its ticket', async () => {
    const named: InboxItem = {
      ...failing,
      main: {
        ...present(failing.main, 'the run'),
        broken_by: '39020b7a40000000000000000000000000000000',
        ticket: 'CF-8',
      },
    }
    const page = await pageOf([named])

    const row = page.get('#main-sample')
    expect(row.text()).toContain('Broken by merge 39020b7a')
    const link = row.findComponent(RouterLinkStub)
    expect(link.text()).toBe('Open CF-8')
    expect(link.props('to')).toBe('/tickets/sample/CF-8')
  })

  test('names a run whose log reports no step as the run', async () => {
    const unnamed: InboxItem = {
      ...failing,
      main: { ...present(failing.main, 'the run'), step: '' },
    }
    const page = await pageOf([unnamed])

    expect(page.get('#main-sample').get('[data-slot="trace-title"]').text()).toBe(
      'sample: the run failed at a5a09a9f',
    )
  })

  test('shows no section while every default branch passes', async () => {
    const page = await pageOf([])

    expect(page.find('#inbox-main').exists()).toBe(false)
    expect(page.text()).toContain('Nothing needs you')
  })
})
