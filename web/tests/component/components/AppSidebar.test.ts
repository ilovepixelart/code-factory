// The sidebar's anatomy (docs/ui.md, The shell): an inset panel beside it, the mark and a
// repository switcher at the top, New ticket and Search as quick actions with their keys, the
// pages grouped by what they are for, and the shortcut sheet, the theme and the owner at the foot.

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { h, ref } from 'vue'
import { SidebarProvider } from '@/components/ui/sidebar'
import { ATTENTION, type Attention } from '@/lib/attention'
import { SHELL } from '@/lib/shell'
import { answer, memoryRouter, stubFetch } from '../../support/board'
import { INLINE, menuItem, openMenu } from '../../support/overlay'
import AppSidebar from '@/components/AppSidebar.vue'

const shell = { search: vi.fn(), newTicket: vi.fn(), shortcuts: vi.fn(), toggleTheme: vi.fn() }
let wrapper: VueWrapper | null = null

async function sidebarAt(address: string): Promise<VueWrapper> {
  const router = memoryRouter([{ path: '/:rest(.*)*', component: { render: () => h('p') } }])
  await router.push(address)
  const attention = { count: ref(2), latest: ref('') } as unknown as Attention
  wrapper = mount(
    { render: () => h(SidebarProvider, () => h(AppSidebar, { darkTheme: true })) },
    {
      attachTo: document.body,
      global: {
        plugins: [router],
        provide: { [SHELL as symbol]: shell, [ATTENTION as symbol]: attention },
        stubs: INLINE,
      },
    },
  )
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  stubFetch((url) => answer(url === '/api/repositories' ? ['shop-api', 'web'] : {}))
})

afterEach(() => {
  wrapper?.unmount()
  wrapper = null
  vi.clearAllMocks()
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

test('the_sidebar_is_inset_so_the_page_sits_on_one_panel_beside_it', async () => {
  const view = await sidebarAt('/tickets')

  expect(view.get('[data-slot="sidebar"]').attributes('data-variant')).toBe('inset')
})

test('the_pages_are_grouped_by_what_they_are_for', async () => {
  const view = await sidebarAt('/tickets')
  const groups = view.findAll('nav[aria-label="Pages"] [data-slot="sidebar-group"]')

  expect(groups).toHaveLength(3)
  expect(
    groups.map((group) => [
      group.attributes('aria-label'),
      group.get('[data-slot="sidebar-group-label"]').text(),
      group.findAll('a').map((a) => a.text()),
    ]),
  ).toEqual([
    ['Work', 'Work', ['Tickets', 'Inbox']],
    ['Agents', 'Agents', ['Sessions', 'Agents', 'Team']],
    ['Insights', 'Insights', ['Analytics', 'Archive', 'Memory']],
  ])
})

// The quick actions are their names alone; their keys are announced, not drawn as chips.
test('new_ticket_then_search_are_quick_actions_that_announce_their_keys', async () => {
  const view = await sidebarAt('/tickets')
  const actions = view.get('[data-quick-actions]')

  await actions.get('[data-action="search"]').trigger('click')
  await actions.get('[data-action="new-ticket"]').trigger('click')

  expect({
    actions: actions
      .findAll('button')
      .map((b) => [b.text().trim(), b.attributes('aria-keyshortcuts')]),
    chips: view.findAll('[data-slot="sidebar"] [data-slot="kbd"]').length,
    calls: [shell.search.mock.calls.length, shell.newTicket.mock.calls.length],
  }).toEqual({
    actions: [
      ['New ticket', 'n'],
      ['Search', 'Meta+K'],
    ],
    chips: 0,
    calls: [1, 1],
  })
})

test('the_repository_switcher_lists_all_then_each_tracked_repository_as_a_board_filter', async () => {
  const view = await sidebarAt('/tickets?repository=web')

  expect(view.get('[data-repository-switcher]').text()).toContain('web')
  await openMenu(view, '[data-repository-switcher]')
  const items = ['All repositories', 'shop-api', 'web'].map((name) => menuItem(view, name))

  expect(items.map((item) => item.attributes('href'))).toEqual([
    '/tickets',
    '/tickets?repository=shop-api',
    '/tickets?repository=web',
  ])
})

test('the_foot_opens_the_shortcut_sheet_and_switches_the_theme', async () => {
  const view = await sidebarAt('/tickets')
  const foot = view.get('[data-slot="sidebar-footer"]')

  await foot.get('[data-action="shortcuts"]').trigger('click')
  await foot.get('[data-action="theme"]').trigger('click')

  expect([shell.shortcuts.mock.calls.length, shell.toggleTheme.mock.calls.length]).toEqual([1, 1])
  // The foot is the two things that act; an Owner line that did nothing is gone.
  expect(
    foot
      .findAll('[data-slot="sidebar-menu-item"]')
      .map(
        (item) =>
          item.attributes('data-action') ?? item.find('[data-action]').attributes('data-action'),
      ),
  ).toEqual(['shortcuts', 'theme'])
})
