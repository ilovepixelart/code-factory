// @vitest-environment happy-dom

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { goldenBoard, memoryRouter, spiedBoard } from '../test/board'
import { view } from '../test/ticketForm'
import TicketForm from './TicketForm.vue'

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

// CF-471: a ticket whose answer is slow still fills the form; the board's own first read lands
// while the ticket is being read, and that later read of the ticket must not leave the fields empty.
describe('a slow ticket answer', () => {
  const reported = {
    ...(view as { ticket: Record<string, unknown> }),
    ticket: {
      ...(view as { ticket: Record<string, unknown> }).ticket,
      title: 'The ticket page sometimes shows an empty title',
      type: 'bug',
      priority: 'high',
    },
  }

  /** The form over a server that holds every ticket read until `release` answers them in order. */
  function slowForm() {
    const held: (() => void)[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            held.push(() => {
              resolve(new Response(JSON.stringify(reported), { status: 200 }))
            })
          }),
      ),
    )
    const live = spiedBoard()
    document.body.innerHTML = '<div id="app"></div>'
    const router = memoryRouter([{ path: '/', component: { template: '<div />' } }])
    const page = mount(TicketForm, {
      attachTo: '#app',
      props: { repository: 'sample', id: 'CF-1', page: true },
      global: {
        plugins: [router],
        provide: live.provide,
        stubs: { RouterLink: true, TicketChanges: true },
      },
    })
    const release = async (): Promise<void> => {
      for (const answer of held.splice(0)) answer()
      await flushPromises()
    }
    return { page, live: live.live, release }
  }

  // CF-487: until the first answer the page says the ticket is loading, not an empty page.
  test('the_ticket_form_shows_loading_until_its_first_answer', async () => {
    const { page, release } = slowForm()
    await flushPromises()

    expect(page.text()).toContain('Reading the ticket')
    expect(page.find('form').exists()).toBe(false)
    await release()
    expect(page.get('form').attributes('aria-label')).toBe('Edit ticket CF-1')
    expect(page.text()).not.toContain('Reading the ticket')
    page.unmount()
  })

  test('a_ticket_read_while_the_board_arrives_fills_the_form', async () => {
    const { page, live, release } = slowForm()
    await flushPromises()
    live.board.value = goldenBoard()
    await flushPromises()
    await release()

    expect((page.get('textarea[name="title"]').element as HTMLTextAreaElement).value).toBe(
      'The ticket page sometimes shows an empty title',
    )
    expect((page.get('#CF-1-type').element as HTMLSelectElement).value).toBe('bug')
    expect((page.get('#CF-1-priority').element as HTMLSelectElement).value).toBe('high')
    page.unmount()
  })

  test('typing_survives_a_later_reading', async () => {
    const { page, live, release } = slowForm()
    await release()
    await page.get('textarea[name="title"]').setValue('typed meanwhile')

    live.board.value = goldenBoard()
    await flushPromises()
    await release()

    expect((page.get('textarea[name="title"]').element as HTMLTextAreaElement).value).toBe(
      'typed meanwhile',
    )
    page.unmount()
  })
})

describe('a ticket whose read fails', () => {
  function failing(status: number | null) {
    let healthy = false
    vi.stubGlobal(
      'fetch',
      vi.fn(() => {
        if (healthy) return Promise.resolve(new Response(JSON.stringify(view), { status: 200 }))
        return status === null
          ? Promise.reject(new TypeError('Failed to fetch'))
          : Promise.resolve(new Response('{"error":"boom"}', { status }))
      }),
    )
    document.body.innerHTML = '<div id="app"></div>'
    const page = mount(TicketForm, {
      attachTo: '#app',
      props: { repository: 'sample', id: 'CF-1', page: true },
      global: {
        plugins: [memoryRouter([{ path: '/', component: { template: '<div />' } }])],
        provide: spiedBoard().provide,
        stubs: { RouterLink: true, TicketChanges: true },
      },
    })
    return {
      page,
      recover: () => {
        healthy = true
      },
    }
  }

  test.each([
    ['an_answer_of_500', 500],
    ['a_dropped_connection', null],
  ])('%s_says_so_and_offers_to_read_again', async (_name, status) => {
    const { page } = failing(status)
    await flushPromises()

    expect(page.get('[role="alert"]').text()).toContain('The board did not answer; try again.')
    expect(page.text()).not.toContain('Reading the ticket')
    expect(page.find('form').exists()).toBe(false)
    page.unmount()
  })

  test('reading_again_fills_the_form', async () => {
    const { page, recover } = failing(500)
    await flushPromises()
    recover()

    await page.get('[data-read-again]').trigger('click')
    await flushPromises()

    expect(page.get('form').attributes('aria-label')).toBe('Edit ticket CF-1')
    expect(page.find('[role="alert"]').exists()).toBe(false)
    page.unmount()
  })
})
