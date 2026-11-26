// CF-364: docs/ui.md (The kanban), a ticket's own page at /tickets/<repository>/<id> shows the
// panel's form in page mode, says so inside the layout when the ticket is missing, and shows the
// branch's Changes below the fields, read again with every reading of the ticket.

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { defineComponent, h, onMounted, ref, type SetupContext } from 'vue'
import type { TicketView } from '@/lib/ticket'
import { memoryRouter } from '../../support/board'
import { present } from '../../support/present'
import TicketPage from '@/pages/TicketPage.vue'

const refresh = vi.fn(() => Promise.resolve())

const FormStub = {
  name: 'TicketForm',
  props: {
    id: { type: String, required: true },
    repository: { type: String, required: true },
    page: Boolean,
  },
  setup(_: unknown, { expose, slots }: SetupContext) {
    expose({ refresh })
    return () => h('div', { id: 'form' }, slots.default?.())
  },
}

const ChangesStub = {
  name: 'TicketChanges',
  props: {
    id: { type: String, required: true },
    repository: { type: String, required: true },
    revision: { type: Number, required: true },
  },
  setup: () => () => h('section', { id: 'changes' }),
}

const read = (branch: string) => ({ ticket: { branch } }) as unknown as TicketView

async function pageAt(address: string) {
  document.body.innerHTML = '<div id="header-title"></div><div id="app"></div>'
  const router = memoryRouter([
    { path: '/tickets/:repository/:id', component: TicketPage },
    { path: '/:rest(.*)*', component: { render: () => null } },
  ])
  await router.push(address)
  const page = mount(TicketPage, {
    attachTo: '#app',
    global: {
      plugins: [router],
      stubs: { TicketForm: FormStub, TicketChanges: ChangesStub, TicketPreview: true },
    },
  })
  await flushPromises()
  return { page, router }
}

afterEach(() => {
  refresh.mockClear()
  document.body.innerHTML = ''
})

describe('the ticket page', () => {
  test('the_breadcrumb_leads_back_to_the_tickets_and_names_the_ticket', async () => {
    await pageAt('/tickets/sample/CF-9')
    const crumb = present(
      document.querySelector('#header-title nav[data-slot="breadcrumb"]'),
      'the breadcrumb',
    )

    expect(crumb.querySelector('a')?.getAttribute('href')).toBe('/tickets')
    expect(crumb.querySelector('h1')?.textContent.trim()).toBe('CF-9')
  })

  test('the_form_shows_the_ticket_the_address_names_in_page_mode', async () => {
    const { page } = await pageAt('/tickets/r%23x/CF-9')

    expect(page.findComponent(FormStub).props()).toEqual({
      id: 'CF-9',
      repository: 'r#x',
      page: true,
    })
  })

  test('a_missing_ticket_says_so_inside_the_page', async () => {
    const { page } = await pageAt('/tickets/sample/CF-404')

    page.findComponent(FormStub).vm.$emit('missing')
    await flushPromises()

    expect(page.text()).toContain('No ticket CF-404')
    expect(page.find('#form').exists()).toBe(false)
  })

  test('a_missing_ticket_links_back_to_the_tickets_inside_the_page', async () => {
    const { page } = await pageAt('/tickets/sample/CF-404')

    page.findComponent(FormStub).vm.$emit('missing')
    await flushPromises()

    const links = page.findAll('a').filter((a) => a.text() === 'Tickets')
    expect(links.map((a) => a.attributes('href'))).toEqual(['/tickets'])
  })

  test('a_ticket_without_a_branch_shows_no_changes', async () => {
    const { page } = await pageAt('/tickets/sample/CF-9')

    page.findComponent(FormStub).vm.$emit('loaded', read(''))
    await flushPromises()

    expect(page.findComponent(ChangesStub).exists()).toBe(false)
  })

  test('a_ticket_with_a_branch_shows_its_changes_read_again_with_every_reading', async () => {
    const { page } = await pageAt('/tickets/sample/CF-9')
    const form = page.findComponent(FormStub)

    form.vm.$emit('loaded', read('feature/CF-9'))
    await flushPromises()
    const first = { ...page.findComponent(ChangesStub).props() }
    form.vm.$emit('loaded', read('feature/CF-9'))
    await flushPromises()

    expect(first).toEqual({ id: 'CF-9', repository: 'sample', revision: 1 })
    expect(page.findComponent(ChangesStub).props('revision')).toBe(2)
  })

  test('a_comment_on_a_line_reads_the_ticket_again', async () => {
    const { page } = await pageAt('/tickets/sample/CF-9')
    page.findComponent(FormStub).vm.$emit('loaded', read('feature/CF-9'))
    await flushPromises()

    page.findComponent(ChangesStub).vm.$emit('commented')
    await flushPromises()

    expect(refresh).toHaveBeenCalledTimes(1)
  })

  test('another_ticket_starts_without_the_last_ones_state', async () => {
    const { page, router } = await pageAt('/tickets/sample/CF-404')
    page.findComponent(FormStub).vm.$emit('missing')
    await flushPromises()

    await router.push('/tickets/sample/CF-9')
    await flushPromises()

    expect(page.find('#form').exists()).toBe(true)
    expect(page.text()).not.toContain('No ticket')
  })

  test('another_ticket_shows_no_changes_until_it_is_read', async () => {
    const { page, router } = await pageAt('/tickets/sample/CF-9')
    page.findComponent(FormStub).vm.$emit('loaded', read('feature/CF-9'))
    await flushPromises()

    await router.push('/tickets/sample/CF-10')
    await flushPromises()

    expect(page.findComponent(ChangesStub).exists()).toBe(false)
  })
})

// CF-562: a form keeps what it read until it reads again, so one reused across tickets would show
// the old ticket while its changes go to the new one.
const HoldingStub = defineComponent({
  name: 'TicketForm',
  props: {
    id: { type: String, required: true },
    repository: { type: String, required: true },
    page: Boolean,
  },
  setup(props) {
    const read = ref('')
    onMounted(() => {
      read.value = props.id
    })
    return () => h('div', { id: 'form' }, `holding ${read.value}`)
  },
})

describe('moving between tickets', () => {
  test('the_form_never_shows_one_ticket_while_the_address_names_another', async () => {
    document.body.innerHTML = '<div id="header-title"></div><div id="app"></div>'
    const router = memoryRouter([
      { path: '/tickets/:repository/:id', component: TicketPage },
      { path: '/:rest(.*)*', component: { render: () => null } },
    ])
    await router.push('/tickets/sample/CF-9')
    const page = mount(TicketPage, {
      attachTo: '#app',
      global: { plugins: [router], stubs: { TicketForm: HoldingStub, TicketChanges: ChangesStub } },
    })
    await flushPromises()

    await router.push('/tickets/sample/CF-10')
    await flushPromises()

    expect(page.find('#form').text()).toBe('holding CF-10')
  })
})
