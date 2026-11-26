// The link picker takes the keyboard when it opens and gives it back to "Link a ticket" when it
// closes, so typing and tabbing continue where the person was.

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, test, vi } from 'vitest'
import TicketForm from '@/components/TicketForm.vue'
import { answer, golden, memoryRouter, provideBoard } from '../../../support/board'
import { present } from '../../../support/present'

const views = golden('tickets.golden.json') as { view: unknown }[]

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

async function shown() {
  vi.stubGlobal(
    'fetch',
    vi.fn((_url: string, init?: RequestInit) =>
      Promise.resolve(
        init?.method === 'POST' ? answer({ notice: 'Linked', undo: null }) : answer(views[0]?.view),
      ),
    ),
  )
  document.body.innerHTML = '<div id="app"></div>'
  const router = memoryRouter([{ path: '/', component: { template: '<div />' } }])
  const page = mount(TicketForm, {
    attachTo: '#app',
    props: { repository: 'sample', id: 'CF-1', page: true },
    global: {
      plugins: [router],
      provide: provideBoard(),
      stubs: { RouterLink: true, TicketChanges: true },
    },
  })
  await flushPromises()
  const opener = present(
    page.findAll('button').find((b) => b.text().includes('Link a ticket')),
    'Link a ticket',
  )
  return { page, opener }
}

const SEARCH = 'input[aria-label="Find a ticket by id or title"]'

test('opening_the_picker_focuses_its_search', async () => {
  const { page, opener } = await shown()

  await opener.trigger('click')
  await flushPromises()

  expect(document.activeElement).toBe(page.get(SEARCH).element)
  page.unmount()
})

test('adding_a_link_returns_focus_to_link_a_ticket', async () => {
  const { page, opener } = await shown()
  await opener.trigger('click')
  await flushPromises()

  await page.get(SEARCH).trigger('keydown', { key: 'Enter' })
  await flushPromises()

  expect(page.find(SEARCH).exists()).toBe(false)
  expect(document.activeElement).toBe(opener.element)
  page.unmount()
})

test('escape_in_the_picker_returns_focus_to_link_a_ticket', async () => {
  const { page, opener } = await shown()
  await opener.trigger('click')
  await flushPromises()

  await page.get(SEARCH).trigger('keydown', { key: 'Escape' })
  await flushPromises()

  expect(page.find(SEARCH).exists()).toBe(false)
  expect(document.activeElement).toBe(opener.element)
  page.unmount()
})

// axe aria-required-attr: an expanded combobox names the list it controls.
test('the_open_picker_search_controls_its_list_of_matches', async () => {
  const { page, opener } = await shown()
  await opener.trigger('click')
  await flushPromises()

  const controls = page.get(SEARCH).attributes('aria-controls') ?? ''
  expect(controls).not.toBe('')
  expect(document.getElementById(controls)?.getAttribute('aria-label')).toBe('Matching tickets')
  page.unmount()
})
