// @vitest-environment happy-dom

import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { usePaged } from '../lib/paging'
import { expect, test } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { memoryRouter } from '../test/board'
import PageNav from './PageNav.vue'
import { INLINE, menuItem, openMenu } from '../test/overlay'

async function nav(
  props: { total: number; page: number; size: number; prefix?: string; fallback?: number },
  at = '/archive?q=gate&page=2&size=10',
) {
  const router = memoryRouter()
  await router.push(at)
  return mount(PageNav, {
    props: { label: 'archived tickets', ...props },
    global: { plugins: [router], stubs: INLINE },
  })
}

// CF-1191-R1: page 2 of 247 rows at 10: the range, the links, the current page and the sizes.
test('page_nav_draws_range_pages_and_sizes', async () => {
  const view = await nav({ total: 247, page: 2, size: 10 })
  const control = view.get('nav')

  expect(control.attributes('aria-label')).toBe('Pages of archived tickets')
  expect(view.get('[data-testid=page-range]').text()).toBe('11 to 20 of 247')
  const numbers = view.findAll('[data-testid=page-number]').map((n) => n.text())
  expect(numbers).toEqual(['1', '2', '3', 'More pages', '25'])
  const current = view.findAll('[aria-current="page"]')
  expect(current.map((c) => c.text())).toEqual(['2'])
  const href = (text: string) =>
    view
      .findAll('a')
      .find((a) => a.text() === text)
      ?.attributes('href')
  expect(href('1')).toBe('/archive?q=gate&size=10')
  expect(href('3')).toBe('/archive?q=gate&page=3&size=10')
  expect(href('25')).toBe('/archive?q=gate&page=25&size=10')
  expect(href('Previous')).toBe('/archive?q=gate&size=10')
  expect(href('Next')).toBe('/archive?q=gate&page=3&size=10')
  expect(view.get('[data-testid=page-of]').text()).toBe('Page 2 of 25')
  expect(view.get('[data-testid=page-size]').text()).toBe('10 per page')
  await openMenu(view, '[data-testid=page-size]')
  const sizes = view.findAll('[role="menuitem"]').map((a) => [a.text(), a.attributes('href')])
  expect(sizes).toEqual([
    ['10 per page', '/archive?q=gate&size=10'],
    ['25 per page', '/archive?q=gate&size=25'],
    ['50 per page', '/archive?q=gate'],
    ['100 per page', '/archive?q=gate&size=100'],
  ])
})

// CF-1191-R1: on the first page Previous, and on the last Next, is a disabled button, not a link.
test('the_ends_have_no_link_beyond_them', async () => {
  const first = await nav({ total: 247, page: 1, size: 10 })
  const last = await nav({ total: 247, page: 25, size: 10 })
  const links = (view: Awaited<ReturnType<typeof nav>>) => view.findAll('a').map((a) => a.text())
  const disabled = (view: Awaited<ReturnType<typeof nav>>) =>
    view.findAll('button[disabled]').map((b) => b.attributes('aria-label'))

  expect(links(first)).not.toContain('Previous')
  expect(disabled(first)).toEqual(['Previous Page'])
  expect(links(first)).toContain('Next')
  expect(links(last)).toContain('Previous')
  expect(links(last)).not.toContain('Next')
  expect(disabled(last)).toEqual(['Next Page'])
  expect(last.get('[data-testid=page-range]').text()).toBe('241 to 247 of 247')
})

// CF-1191-R2: a list that fits one page, or holds nothing, draws no control.
test('page_nav_hidden_on_a_single_page', async () => {
  expect((await nav({ total: 10, page: 1, size: 10 })).find('nav').exists()).toBe(false)
  expect((await nav({ total: 0, page: 1, size: 50 })).find('nav').exists()).toBe(false)
  expect((await nav({ total: 11, page: 1, size: 10 })).find('nav').exists()).toBe(true)
  // A page past the one a short list holds still shows the way back.
  expect((await nav({ total: 4, page: 2, size: 10 })).find('nav').exists()).toBe(true)
})

// CF-1191-R3: a list with a prefix writes only its own keys.
test('a_prefixed_list_links_its_own_keys', async () => {
  const view = await nav(
    { total: 30, page: 1, size: 10, prefix: 'factory_', fallback: 10 },
    '/flow?type=bug',
  )
  const next = view.findAll('a').find((a) => a.text() === 'Next')

  expect(next?.attributes('href')).toBe('/flow?type=bug&factory_page=2')
})

// CF-1191-R14: the design page shows the control, and docs/design.md names it.
test('design_doc_and_page_show_the_page_control', () => {
  const root = join(__dirname, '..', '..', '..')
  const design = readFileSync(join(root, 'docs/design.md'), 'utf8')
  const page = readFileSync(join(root, 'web/src/pages/design/DesignComponents.vue'), 'utf8')

  expect(design).toMatch(/\| `PageNav` \(total, page, size, label\) \|/)
  expect(page).toContain('<PageNav')
})

// CF-1191-R5: a list paged in the browser past its last page shows the last and says so in the
// address; while its rows are not read yet it leaves the address alone.
test('a_browser_paged_list_past_its_end_shows_its_last_page', async () => {
  const router = memoryRouter()
  await router.push('/tickets/list?q=x&page=9&size=10')
  const rows = ref<number[] | null>(null)
  const List = defineComponent({
    setup() {
      const paged = usePaged(() => rows.value)
      return () => h('p', paged.rows.value.join(','))
    },
  })
  const view = mount(List, { global: { plugins: [router] } })
  await flushPromises()
  expect(router.currentRoute.value.query.page).toBe('9')

  rows.value = Array.from({ length: 25 }, (_, n) => n + 1)
  await flushPromises()

  expect(view.text()).toBe('21,22,23,24,25')
  expect(router.currentRoute.value.query).toEqual({ q: 'x', page: '3', size: '10' })

  // An address past the end reached while the last page is already drawn is put right too.
  await router.push('/tickets/list?q=x&page=7&size=10')
  await flushPromises()

  expect(router.currentRoute.value.query).toEqual({ q: 'x', page: '3', size: '10' })
})

// CF-1191-R1: picking a size closes the size menu, and Escape closes it.
test('the_size_menu_closes_on_a_pick_and_on_escape', async () => {
  const view = await nav({ total: 247, page: 2, size: 10 }, '/archive?q=gate&page=2&size=10')
  const menu = () => view.find('[role="menu"]').exists()

  await openMenu(view, '[data-testid=page-size]')
  const opened = menu()
  await menuItem(view, '25 per page').trigger('click')
  await flushPromises()
  const afterPick = menu()

  await openMenu(view, '[data-testid=page-size]')
  document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
  await flushPromises()

  expect([opened, afterPick, menu()]).toEqual([true, false, false])
})
