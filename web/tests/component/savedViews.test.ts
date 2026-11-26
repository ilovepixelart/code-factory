import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, test, vi } from 'vitest'
import FilterMenu from '@/components/board/FilterMenu.vue'
import CommandMenu from '@/components/CommandMenu.vue'
import { notice } from '@/lib/notice'
import { answer, memoryRouter } from '../support/board'
import { INLINE, openMenu } from '../support/overlay'

afterEach(() => vi.unstubAllGlobals())

test('saved_view_menus_save_open_delete_and_report_errors', async () => {
  const views: { name: string; query: string }[] = []
  const fetch = vi.fn((_path: string, init?: RequestInit) => {
    if (init?.method === 'POST') views.push(JSON.parse(init.body as string))
    if (init?.method === 'DELETE') views.splice(0)
    return Promise.resolve(answer(init?.method ? {} : [...views]))
  })
  vi.stubGlobal('fetch', fetch)
  const router = memoryRouter()
  const query =
    'type=bug&type=feature&label=ui&priority=high&assignee=AL&repository=sample&blocked=1&questions=1&agent=1&q=hello+world&future=kept'
  await router.push(`/tickets?${query}`)
  const menu = mount(FilterMenu, {
    props: {
      query: [],
      options: {},
      toggleUrl: () => '',
      clearUrl: '/tickets',
    },
    global: { plugins: [router], stubs: INLINE },
  })
  await openMenu(menu, 'button[aria-haspopup="dialog"]')
  await menu.get('input').setValue('Bugs')
  await menu.get('form').trigger('submit')
  await flushPromises()
  expect(views).toStrictEqual([{ name: 'Bugs', query }])
  expect(menu.get('a[href*="future=kept"]').attributes('href')).toBe(`/tickets?${query}`)
  const commands = mount(CommandMenu, {
    global: {
      plugins: [router],
      stubs: INLINE,
    },
  })
  await (commands.vm as unknown as { open: () => Promise<void> }).open()
  await flushPromises()
  expect(commands.text()).toContain('Bugssaved view')
  await menu.get('button[aria-label="Delete view Bugs"]').trigger('click')
  await flushPromises()
  expect(menu.find('a[href*="future=kept"]').exists()).toBe(false)
  expect(commands.text()).not.toContain('Bugssaved view')
  fetch.mockImplementation(() => Promise.resolve(answer({ detail: 'Cannot save view' }, 409)))
  await menu.get('input').setValue('Bugs')
  await menu.get('form').trigger('submit')
  await flushPromises()
  expect((menu.get('input').element as HTMLInputElement).value).toBe('Bugs')
  expect(notice.text).toBe('Cannot save view')
  fetch.mockImplementation(() => Promise.resolve(answer({ unexpected: 'shape' })))
  await (commands.vm as unknown as { open: () => Promise<void> }).open()
  await flushPromises()
  expect(notice.text).toBe('Saved views could not be read')
  expect(commands.text()).toContain('Go to Tickets')
  menu.unmount()
  commands.unmount()
})
