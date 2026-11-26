// @vitest-environment happy-dom
// CF-364: the shell (docs/ui.md): the sidebar's links with the page that is current, the Inbox
// link carrying the count of what waits on you, the live state, the theme and the sidebar fold
// remembered per browser, and the shortcuts, which never fire while the person types, except Cmd+K.

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { defineComponent, h, inject } from 'vue'
import type { Router } from 'vue-router'
import App from './App.vue'
import { ask } from './lib/actions'
import { BOARD } from './lib/live'
import { usePolledRead } from './lib/queries'
import { answer, goldenBoard, memoryRouter, stubFetch } from './test/board'
import { present } from './test/present'

const commandMenu = vi.fn()
const shortcutSheet = vi.fn()
const newTicket = vi.fn()
const exposing = (name: string, open: () => void) =>
  defineComponent({
    name,
    setup(_, { expose }) {
      expose({ open })
      return () => h('div')
    },
  })

const blank = { render: () => h('p', 'page') }
// A page that follows the board, as the board's own pages do, so the shell keeps reading it.
const following = {
  setup() {
    inject(BOARD)?.follow()
    return () => h('p', 'page')
  },
}
// A page with a polled read of its own, as Memory or Team: the shell does not read the board for it.
const reading = {
  setup() {
    usePolledRead(['probe'], (signal) => ask<object>('/api/probe', signal), 3000)
    return () => h('p', 'page')
  },
}
let inbox = { count: 0, latest: '' }
let wrapper: VueWrapper | null = null

async function shellAt(address: string): Promise<{ app: VueWrapper; router: Router }> {
  document.body.innerHTML = '<div id="app"></div>'
  const router = memoryRouter([
    { path: '/', component: blank, meta: { title: 'Sessions' } },
    { path: '/sessions/:id', component: blank, meta: { title: '' } },
    { path: '/tickets', component: blank, meta: { title: 'Tickets' } },
    { path: '/tickets/list', component: blank, meta: { title: 'Tickets' } },
    { path: '/inbox', component: blank, meta: { title: 'Inbox' } },
    { path: '/analytics', component: blank, meta: { title: 'Flow' } },
    { path: '/board', component: following, meta: { title: 'Tickets' } },
    { path: '/memory', component: reading, meta: { title: 'Memory' } },
    { path: '/archive', component: blank, meta: { title: 'Archive' } },
    { path: '/agents', component: blank, meta: { title: 'Agents' } },
    { path: '/team', component: blank, meta: { title: 'Team' } },
  ])
  await router.push(address)
  const app = mount(App, {
    attachTo: '#app',
    global: {
      plugins: [router],
      stubs: {
        CommandMenu: exposing('CommandMenu', commandMenu),
        ShortcutSheet: exposing('ShortcutSheet', shortcutSheet),
        NewTicket: exposing('NewTicket', newTicket),
        ConfirmDialog: true,
        Toaster: true,
      },
    },
  })
  wrapper = app
  await flushPromises()
  return { app, router }
}

const link = (app: VueWrapper, name: string) =>
  present(
    app.findAll('nav[aria-label="Pages"] a').find((a) => a.text() === name),
    `the ${name} link`,
  )
const current = (app: VueWrapper) =>
  app
    .findAll('nav[aria-label="Pages"] a')
    .filter((a) => a.attributes('aria-current') === 'page')
    .map((a) => a.text())

function key(key: string, init: KeyboardEventInit = {}, target: Element = document.body) {
  const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...init })
  target.dispatchEvent(event)
  return event
}

beforeEach(() => {
  inbox = { count: 0, latest: '' }
  stubFetch((url) => (url === '/api/inbox/count' ? answer(inbox) : answer(goldenBoard())))
  localStorage.clear()
  document.documentElement.className = ''
  delete document.documentElement.dataset.sidebar
})

afterEach(() => {
  wrapper?.unmount()
  wrapper = null
  vi.restoreAllMocks()
  vi.useRealTimers()
  vi.unstubAllGlobals()
  commandMenu.mockClear()
  shortcutSheet.mockClear()
  newTicket.mockClear()
  document.body.innerHTML = ''
})

// WCAG 2.4.1: the first Tab stop skips the sidebar to the page, and nothing sits outside a landmark.
describe('the way past the sidebar', () => {
  test('the_first_tab_stop_skips_to_the_main_content', async () => {
    await shellAt('/analytics')
    const first = present(document.querySelector('a[href], button'), 'the first stop')
    const target = document.getElementById(first.getAttribute('href')?.slice(1) ?? '')

    expect([first.textContent.trim(), target?.tagName, target?.getAttribute('tabindex')]).toEqual([
      'Skip to content',
      'MAIN',
      '-1',
    ])
  })

  test('the_brand_and_the_theme_sit_inside_the_sidebar_landmark', async () => {
    const { app } = await shellAt('/analytics')
    const landmark = (element: Element) => element.closest('aside, nav, main')?.tagName

    expect([
      landmark(present(app.find('[data-repository-switcher] .truncate').element, 'the brand')),
      landmark(app.get('button[aria-label="Dark theme"]').element),
    ]).toEqual(['ASIDE', 'ASIDE'])
  })
})

describe('the sidebar', () => {
  // CF-836-R2: absolutely positioned text inside a page (screen-reader text) is placed against the
  // scroller, not the document, so a long page never grows the document past the window.
  test('the_scroller_holds_what_it_positions', async () => {
    const { app } = await shellAt('/')

    expect(app.get('[data-scroller]').classes()).toContain('relative')
  })

  // The logo is the product's mark beside its name, not letters in a square.
  // sidebar-07's switcher: the mark beside the board's name, over the repository in view.
  test('the_logo_is_the_mark_beside_the_name', async () => {
    const { app } = await shellAt('/')
    const brand = app.get('[data-slot="sidebar-header"] [data-repository-switcher]')
    const lines = brand.findAll('.truncate').map((line) => line.text())

    expect(lines).toEqual(['Code Factory', 'All repositories'])
    expect(brand.get('svg').attributes('viewBox')).toBe('0 0 32 32')
    expect(brand.findAll('svg circle')).toHaveLength(3)
  })

  test('the_page_title_is_the_routes_title', async () => {
    const { app } = await shellAt('/analytics')

    expect(app.get('header h1').text()).toBe('Flow')
  })

  test('the_tab_title_names_the_page_with_the_inbox_count', async () => {
    inbox = { count: 6, latest: '' }
    await shellAt('/analytics')

    expect(document.title).toBe('(6) Flow · code-factory')
  })

  test('the_tab_title_of_a_page_without_a_title_names_what_its_address_opens', async () => {
    inbox = { count: 6, latest: '' }
    await shellAt('/sessions/demo-search-rank')

    expect(document.title).toBe('(6) demo-search-rank · code-factory')
  })

  test('a_page_without_a_title_shows_none', async () => {
    const { app } = await shellAt('/sessions/s-1')

    expect(app.find('header h1').exists()).toBe(false)
  })

  test('sessions_is_current_on_the_sessions_page_and_on_a_session', async () => {
    const home = await shellAt('/')
    const onHome = current(home.app)
    home.app.unmount()
    const { app } = await shellAt('/sessions/s-1')

    expect(onHome).toEqual(['Sessions'])
    expect(current(app)).toEqual(['Sessions'])
  })

  test('a_page_is_current_on_its_own_address_and_below_it', async () => {
    const { app } = await shellAt('/tickets/list')

    expect(current(app)).toEqual(['Tickets'])
  })

  // An address with no page (Not found) marks no page current, even when it starts like one.
  test('an_address_without_a_page_marks_none_current', async () => {
    const sessions = await shellAt('/sessions')
    const onSessions = current(sessions.app)
    sessions.app.unmount()
    const { app } = await shellAt('/ticketsx')

    expect([onSessions, current(app)]).toEqual([[], []])
  })

  test('the_inbox_link_names_how_many_things_wait', async () => {
    inbox = { count: 3, latest: 'CF-9 asks a question' }
    const { app } = await shellAt('/analytics')
    const inboxLink = link(app, 'Inbox')
    const item = present(inboxLink.element.closest('li'), 'the Inbox item')

    expect(inboxLink.attributes('aria-label')).toBe('Inbox, 3 waiting')
    expect(item.querySelector('[data-slot="sidebar-menu-badge"]')?.textContent).toBe('3')
    expect(item.querySelector('[data-testid="inbox-dot"]')).not.toBeNull()
    expect(
      Object.fromEntries(
        ['data-attention', 'data-latest'].map((name) => [
          name,
          present(item.querySelector('[data-attention]'), 'the count').getAttribute(name),
        ]),
      ),
    ).toMatchObject({
      'data-attention': '3',
      'data-latest': 'CF-9 asks a question',
    })
  })

  test('nothing_waiting_leaves_the_inbox_link_plain', async () => {
    const { app } = await shellAt('/analytics')
    const inboxLink = link(app, 'Inbox')

    const item = present(inboxLink.element.closest('li'), 'the Inbox item')

    expect(inboxLink.attributes('aria-label')).toBe('Inbox')
    expect(item.querySelector('[data-attention]')?.getAttribute('data-attention')).toBe('0')
    expect(item.querySelector('[data-slot="sidebar-menu-badge"]')).toBeNull()
    expect(item.querySelector('[data-testid="inbox-dot"]')).toBeNull()
  })

  test('the_header_says_the_board_is_live_once_it_answered', async () => {
    const { app } = await shellAt('/analytics')

    expect(app.get('header [aria-live="polite"]').text()).toBe('live')
  })
})

// The owner: the header's dot tells live and reconnecting apart by its colour alone; a browser the
// board refuses has no dot, since nothing it shows is live.
describe('the live dot', () => {
  const dot = (app: VueWrapper) => app.get('header [data-testid="live-dot"]')
  let reply: 'board' | 'fails' | 'refused' = 'board'
  const replies = (url: string) => {
    if (url === '/api/inbox/count') return answer(inbox)
    if (reply === 'refused') return answer({ detail: 'this host is not answered' }, 403)
    return reply === 'fails' ? answer({ detail: 'down' }, 500) : answer(goldenBoard())
  }
  async function dotAt(
    state: typeof reply,
  ): Promise<{ state: string | undefined; colour: string }> {
    vi.useFakeTimers()
    reply = state === 'refused' ? 'refused' : 'board'
    stubFetch(replies)
    const { app } = await shellAt('/board')
    if (state === 'fails') {
      reply = 'fails'
      await vi.advanceTimersByTimeAsync(3000)
      await flushPromises()
    }
    const element = dot(app)
    return { state: element.attributes('data-state'), colour: element.classes().join(' ') }
  }

  test('the_dot_says_live_once_the_board_answered', async () => {
    expect((await dotAt('board')).state).toBe('live')
  })

  test('the_dot_says_reconnecting_when_a_read_fails_after_an_answer', async () => {
    expect((await dotAt('fails')).state).toBe('reconnecting')
  })

  test('a_refused_browser_has_no_dot', async () => {
    vi.useFakeTimers()
    reply = 'refused'
    stubFetch(replies)
    const { app } = await shellAt('/board')

    expect(app.find('header [data-testid="live-dot"]').exists()).toBe(false)
  })

  test('live_and_reconnecting_each_draw_the_dot_in_another_colour', async () => {
    const colours = []
    for (const state of ['board', 'fails'] as const) {
      colours.push((await dotAt(state)).colour)
      wrapper?.unmount()
      wrapper = null
      vi.useRealTimers()
    }

    expect(new Set(colours).size).toBe(2)
  })
})

// A page's own polled read that the board does not answer tells in the header, as the board's does,
// and the page's figures are said to be its last read; a refusal is an answer and does not.
describe('a page read the board does not answer', () => {
  let probe: 'answers' | 'unreachable' | 'refuses' = 'answers'
  async function memoryAfter(next: typeof probe): Promise<VueWrapper> {
    vi.useFakeTimers({ toFake: ['setTimeout', 'setInterval', 'Date'] })
    vi.setSystemTime(new Date(2026, 10, 24, 19, 6, 0))
    probe = 'answers'
    stubFetch((url) => {
      if (url === '/api/inbox/count') return answer(inbox)
      if (url !== '/api/probe') return answer(goldenBoard())
      if (probe === 'unreachable') throw new TypeError('Failed to fetch')
      return probe === 'refuses' ? answer({ detail: 'the ledger is unreadable' }, 500) : answer({})
    })
    const { app } = await shellAt('/memory')
    probe = next
    await vi.advanceTimersByTimeAsync(3000)
    await flushPromises()
    return app
  }
  const status = (app: VueWrapper) => app.get('header [aria-live="polite"]').text()

  test('the_header_says_reconnecting_and_when_the_page_was_last_read', async () => {
    const app = await memoryAfter('unreachable')

    expect([status(app), app.get('header [data-testid="last-read"]').text()]).toEqual([
      'reconnecting',
      'The board did not answer; this page shows its last read, from 19:06.',
    ])
  })

  test('a_refused_page_read_leaves_the_header_live', async () => {
    const app = await memoryAfter('refuses')

    expect([status(app), app.find('header [data-testid="last-read"]').exists()]).toEqual([
      'live',
      false,
    ])
  })

  test('the_next_answer_takes_the_notice_away', async () => {
    const app = await memoryAfter('unreachable')
    probe = 'answers'
    await vi.advanceTimersByTimeAsync(3000)
    await flushPromises()

    expect([status(app), app.find('header [data-testid="last-read"]').exists()]).toEqual([
      'live',
      false,
    ])
  })
})

describe('a browser that is not signed in', () => {
  const READ_REFUSAL = "reading the board needs the owner's sign-in: run uv run code-factory open"
  let signed = false
  const signedOrRefused = (url: string) =>
    signed
      ? answer(url === '/api/inbox/count' ? inbox : goldenBoard())
      : answer({ detail: READ_REFUSAL }, 403)

  // CF-1178-R1: every page of the shell gives way to the board's reason and how to sign in.
  // The way to sign in is uv run code-factory open, or the link sign-in prints.
  test('a_signed_out_browser_is_told_how_to_sign_in', async () => {
    signed = false
    stubFetch(signedOrRefused)
    const { app } = await shellAt('/inbox')
    const notice = app.get('main [role="alert"]')

    const parts = ['card-title', 'card-description'].map((slot) =>
      notice.get(`[data-slot="${slot}"]`).text().replace(/\s+/g, ' ').trim(),
    )

    expect(notice.attributes('aria-labelledby')).toBe('sign-in-heading')
    expect(parts).toEqual([
      'This browser is not signed in',
      "Reading the board needs the owner's sign-in.",
    ])
    expect(notice.findAll('code').map((command) => command.text())).toEqual([
      'uv run code-factory open',
      'uv run code-factory sign-in',
    ])
    expect(notice.get('[aria-label="This browser"]').text()).toContain('within 60 seconds')
    expect(notice.findAll('button[aria-label="Copy"]')).toHaveLength(2)
    expect(app.get('[data-scroller]').text()).not.toContain('page')
  })

  // A backdrop of its own stopped short of the page area's scrollbar gutters on either side.
  test('the_sign_in_card_sits_on_the_page_background', async () => {
    stubFetch(() => answer({ detail: 'this host is not answered' }, 403))
    const { app } = await shellAt('/inbox')
    const backdrop = present(
      app.get('main [role="alert"]').element.parentElement?.parentElement,
      'its frame',
    )

    expect(backdrop.className).not.toMatch(/\bbg-/)
  })

  // Another 403 reason is shown as the board worded it, capitalised, and is not called a sign-in.
  test('another_refusal_is_shown_as_the_board_worded_it', async () => {
    stubFetch(() => answer({ detail: 'this host is not answered' }, 403))
    const { app } = await shellAt('/inbox')

    expect(app.get('main [role="alert"] [data-slot="card-description"]').text()).toBe(
      'This host is not answered',
    )
    expect(app.get('header [aria-live="polite"]').text()).toBe('signed out')
  })

  // The header does not say `connecting` or name the page it cannot show while the board refuses
  // the read: it reads Sign in, signed out, as the card under it does.
  test('the_header_says_sign_in_while_the_read_is_refused_and_the_page_after', async () => {
    vi.useFakeTimers()
    signed = false
    stubFetch(signedOrRefused)
    const { app } = await shellAt('/analytics')
    const words = () =>
      `${app.get('header h1').text()} ${app.get('header [aria-live="polite"]').text()}`
    const refused = words()

    signed = true
    await vi.advanceTimersByTimeAsync(3000)
    await flushPromises()

    expect([refused, words()]).toStrictEqual(['Sign in signed out', 'Flow live'])
  })

  // CF-1178-R2: the next answered read takes the notice away and shows the page, with no reload.
  test('signing_in_brings_the_page_back', async () => {
    vi.useFakeTimers()
    signed = false
    stubFetch(signedOrRefused)
    const { app } = await shellAt('/analytics')
    const refusedFirst = app.find('main [role="alert"]').exists()

    signed = true
    await vi.advanceTimersByTimeAsync(3000)
    await flushPromises()

    expect(refusedFirst).toBe(true)
    expect(app.find('main [role="alert"]').exists()).toBe(false)
    expect(app.get('[data-scroller]').text()).toBe('page')
  })
})

describe('the navigation on a phone', () => {
  // Below the md breakpoint the sidebar is a sheet: the header's trigger opens it with the pages.
  test('the_header_trigger_opens_the_pages_in_a_sheet_on_a_phone', async () => {
    vi.stubGlobal(
      'matchMedia',
      (query: string) =>
        ({
          matches: query.includes('max-width'),
          media: query,
          addEventListener: () => undefined,
          removeEventListener: () => undefined,
        }) as unknown as MediaQueryList,
    )
    const { app } = await shellAt('/analytics')
    const closed = document.querySelectorAll('nav[aria-label="Pages"]').length

    await app.get('button[title="Toggle sidebar ([)"]').trigger('click')
    await flushPromises()
    const sheet = present(document.querySelector('[role="dialog"]'), 'the sheet')

    expect(closed).toBe(0)
    expect(
      [...sheet.querySelectorAll('nav[aria-label="Pages"] a')].map((a) => a.textContent.trim()),
    ).toEqual(['Tickets', 'Inbox', 'Sessions', 'Agents', 'Team', 'Analytics', 'Archive', 'Memory'])
  })

  // The sheet covers the page: a page chosen in it is shown, not left behind the sheet.
  test('choosing_a_page_in_the_sheet_closes_it', async () => {
    vi.stubGlobal(
      'matchMedia',
      (query: string) =>
        ({
          matches: query.includes('max-width'),
          media: query,
          addEventListener: () => undefined,
          removeEventListener: () => undefined,
        }) as unknown as MediaQueryList,
    )
    const { app, router } = await shellAt('/analytics')
    await app.get('button[title="Toggle sidebar ([)"]').trigger('click')
    await flushPromises()
    const opened = document.querySelectorAll('[role="dialog"]').length

    await router.push('/inbox')
    await flushPromises()

    expect([opened, document.querySelectorAll('[role="dialog"]').length]).toEqual([1, 0])
  })
})

describe('the theme and the sidebar fold', () => {
  test('toggle_theme_switches_to_dark_and_remembers_it', async () => {
    const { app } = await shellAt('/analytics')
    const toggle = app.get('button[aria-label="Dark theme"]')
    const offered = toggle.text()

    await toggle.trigger('click')

    expect(offered).toBe('Dark theme')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
    expect(document.documentElement.dataset.theme).toBeUndefined()
    expect(localStorage.getItem('codeFactoryTheme')).toBe('dark')
    expect(toggle.text()).toBe('Light theme')
  })

  // WCAG 2.5.3: the button's name is the words it shows, also where they are hidden (a phone).
  test('the_theme_button_is_named_by_the_words_it_shows', async () => {
    const { app } = await shellAt('/analytics')
    const toggle = app.get('button[title$="theme"]')
    const dark = [toggle.attributes('aria-label'), toggle.text()]

    await toggle.trigger('click')

    expect(dark).toEqual(['Dark theme', 'Dark theme'])
    expect([toggle.attributes('aria-label'), toggle.text()]).toEqual(['Light theme', 'Light theme'])
  })

  test('a_dark_page_toggles_back_to_light', async () => {
    localStorage.setItem('codeFactoryTheme', 'dark')
    const { app } = await shellAt('/analytics')

    await app.get('button[aria-label="Light theme"]').trigger('click')

    expect(document.documentElement.classList.contains('dark')).toBe(false)
    expect(document.documentElement.dataset.theme).toBeUndefined()
    expect(localStorage.getItem('codeFactoryTheme')).toBe('light')
  })

  const sidebarState = (app: VueWrapper) =>
    app.get('[data-slot="sidebar"]').attributes('data-state')

  // The fold button is named as its tooltip and the shortcut sheet write it.
  test('the_sidebar_fold_is_named_toggle_sidebar', async () => {
    const { app } = await shellAt('/analytics')

    expect(app.get('button[title="Toggle sidebar ([)"]').text()).toBe('Toggle sidebar')
  })

  test('the_sidebar_folds_and_opens_and_remembers_it', async () => {
    const { app } = await shellAt('/analytics')
    const fold = app.get('button[title="Toggle sidebar ([)"]')

    await fold.trigger('click')
    const folded = [
      document.documentElement.dataset.sidebar,
      localStorage.getItem('codeFactorySidebar'),
      sidebarState(app),
    ]
    await fold.trigger('click')

    expect(folded).toEqual(['folded', 'folded', 'collapsed'])
    expect(document.documentElement.dataset.sidebar).toBeUndefined()
    expect(localStorage.getItem('codeFactorySidebar')).toBe('open')
    expect(sidebarState(app)).toBe('expanded')
  })

  // The owner: the sidebar is not resized by dragging its edge; the header trigger folds it.
  test('the_sidebar_has_no_drag_edge_and_folds_from_its_trigger', async () => {
    const { app } = await shellAt('/analytics')

    expect(app.find('[data-slot="sidebar-rail"]').exists()).toBe(false)
    expect(app.find('[data-slot="sidebar-trigger"]').exists()).toBe(true)
  })

  test('a_page_loaded_folded_starts_folded', async () => {
    document.documentElement.dataset.sidebar = 'folded'
    const { app } = await shellAt('/analytics')

    expect(sidebarState(app)).toBe('collapsed')
  })
})

describe('the shortcuts', () => {
  test('cmd_k_opens_the_command_menu_even_from_a_field', async () => {
    await shellAt('/analytics')
    document.body.insertAdjacentHTML('beforeend', '<input id="field" />')

    const event = key('k', { metaKey: true }, present(document.querySelector('#field'), 'field'))
    key('K', { ctrlKey: true })

    expect(commandMenu).toHaveBeenCalledTimes(2)
    expect(event.defaultPrevented).toBe(true)
  })

  test('question_mark_opens_the_shortcut_sheet', async () => {
    await shellAt('/analytics')

    key('?')

    expect(shortcutSheet).toHaveBeenCalledTimes(1)
  })

  test('n_opens_the_new_ticket_form_from_any_page', async () => {
    await shellAt('/analytics')

    const event = key('n')

    expect(newTicket).toHaveBeenCalledTimes(1)
    expect(event.defaultPrevented).toBe(true)
  })

  test('n_is_ignored_in_a_field_with_a_modifier_or_while_a_dialog_is_open', async () => {
    await shellAt('/analytics')
    document.body.insertAdjacentHTML('beforeend', '<input id="field" />')

    key('n', {}, present(document.querySelector('#field'), 'field'))
    key('n', { metaKey: true })
    key('n', { ctrlKey: true })
    key('n', { altKey: true })
    document.body.insertAdjacentHTML('beforeend', '<div role="dialog" data-state="open"></div>')
    key('n')

    expect(newTicket).not.toHaveBeenCalled()
  })

  test('left_bracket_folds_the_sidebar', async () => {
    await shellAt('/analytics')

    key('[')

    expect(document.documentElement.dataset.sidebar).toBe('folded')
  })

  test('g_then_s_goes_to_sessions_and_g_then_t_to_tickets', async () => {
    const { router } = await shellAt('/analytics')

    key('g')
    key('s')
    await flushPromises()
    const afterS = router.currentRoute.value.fullPath
    key('g')
    key('t')
    await flushPromises()

    expect(afterS).toBe('/')
    expect(router.currentRoute.value.fullPath).toBe('/tickets')
  })

  // Every page in the sidebar has its own g key, so no page is reached only by the mouse.
  test('g_then_a_page_key_goes_to_every_page', async () => {
    const { router } = await shellAt('/board')
    const reached: Record<string, string> = {}

    for (const page of ['i', 'a', 'r', 'm', 'g', 'e', 't', 's']) {
      key('g')
      key(page)
      await flushPromises()
      reached[page] = router.currentRoute.value.fullPath
    }

    expect(reached).toEqual({
      i: '/inbox',
      a: '/analytics',
      r: '/archive',
      m: '/memory',
      g: '/agents',
      e: '/team',
      t: '/tickets',
      s: '/',
    })
  })

  test('t_without_g_goes_nowhere', async () => {
    const { router } = await shellAt('/analytics')

    key('t')
    await flushPromises()

    expect(router.currentRoute.value.fullPath).toBe('/analytics')
  })

  test('g_then_t_a_second_later_goes_nowhere', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-10-07T12:00:00.000Z'))
    const { router } = await shellAt('/analytics')

    key('g')
    vi.setSystemTime(new Date('2026-10-07T12:00:01.000Z'))
    key('t')
    await flushPromises()

    expect(router.currentRoute.value.fullPath).toBe('/analytics')
  })

  test('a_shortcut_typed_in_a_field_stays_in_the_field', async () => {
    await shellAt('/analytics')
    document.body.insertAdjacentHTML('beforeend', '<textarea id="text"></textarea>')

    key('?', {}, present(document.querySelector('#text'), 'text'))

    expect(shortcutSheet).not.toHaveBeenCalled()
  })

  test('no_shortcut_fires_while_a_dialog_is_open_or_with_a_modifier', async () => {
    await shellAt('/analytics')

    key('?', { altKey: true })
    key('?', { ctrlKey: true })
    document.body.insertAdjacentHTML('beforeend', '<div role="dialog" data-state="open"></div>')
    key('?')

    expect(shortcutSheet).not.toHaveBeenCalled()
  })

  test('the_shortcuts_stop_with_the_shell', async () => {
    const { app } = await shellAt('/analytics')

    app.unmount()
    wrapper = null
    key('[')

    expect(document.documentElement.dataset.sidebar).toBeUndefined()
  })
})

describe('the page gutter', () => {
  test('the_main_area_measures_its_scrollbar_gutter_per_edge', async () => {
    vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(1000)
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(984)
    const { app } = await shellAt('/analytics')

    expect(
      (app.get('[data-scroller]').element as HTMLElement).style.getPropertyValue('--gutter'),
    ).toBe('8px')
  })

  // CF-847-R6: characterization tests, written against the hand-made observer before it moved to
  // VueUse and passing before and after. happy-dom's ResizeObserver never calls back, so a stand-in
  // records what it observes and is called back by hand.
  class StandInObserver {
    static made: StandInObserver[] = []
    observed: Element[] = []
    disconnected = false
    readonly callback: () => void
    constructor(callback: () => void) {
      this.callback = callback
      StandInObserver.made.push(this)
    }
    observe(target: Element): void {
      this.observed.push(target)
    }
    disconnect(): void {
      this.disconnected = true
    }
  }
  const watching = (main: Element) =>
    present(
      StandInObserver.made.find((made) => made.observed.includes(main)),
      'an observer of main',
    )

  test('the_gutter_is_measured_again_when_the_main_area_resizes', async () => {
    StandInObserver.made = []
    vi.stubGlobal('ResizeObserver', StandInObserver)
    vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(1000)
    const client = vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(984)
    const { app } = await shellAt('/analytics')
    const main = app.get('[data-scroller]').element as HTMLElement

    client.mockReturnValue(1000)
    watching(main).callback()
    await flushPromises()

    expect(main.style.getPropertyValue('--gutter')).toBe('0px')
  })

  test('the_gutter_observer_stops_with_the_shell', async () => {
    StandInObserver.made = []
    vi.stubGlobal('ResizeObserver', StandInObserver)
    const { app } = await shellAt('/analytics')
    const observer = watching(app.get('[data-scroller]').element)

    app.unmount()
    wrapper = null

    expect(observer.disconnected).toBe(true)
  })
})
