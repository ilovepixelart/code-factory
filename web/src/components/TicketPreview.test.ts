// @vitest-environment happy-dom
// CF-1379: a ticket's page offers a live preview only while the repository sets `[preview]
// command`; Preview starts it, and a running one shows its link and Stop.

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { clear } from '../lib/notice'
import { answer, stubFetch } from '../test/board'
import TicketPreview from './TicketPreview.vue'

const STOPPED = { configured: true, running: false, port: null, address: null, idle_seconds: 1800 }
const RUNNING = {
  configured: true,
  running: true,
  port: 4321,
  address: 'http://localhost:4321/',
  idle_seconds: 1800,
}

async function shown(read: () => object) {
  const sent = stubFetch((_, init) =>
    init?.method ? answer({ notice: '', undo: null }) : answer(read()),
  )
  const wrapper = mount(TicketPreview, { props: { repository: 'r', id: 'CF-9' } })
  await flushPromises()
  return { wrapper, sent }
}

afterEach(() => {
  vi.unstubAllGlobals()
  clear()
})

describe('the preview', () => {
  test('nothing_is_drawn_without_a_preview_command', async () => {
    const { wrapper } = await shown(() => ({ ...STOPPED, configured: false }))

    expect(wrapper.html()).toBe('<!--v-if-->')
  })

  test('a_configured_preview_offers_one_button_and_no_link', async () => {
    const { wrapper, sent } = await shown(() => STOPPED)

    expect(wrapper.findAll('button').map((b) => b.text())).toEqual(['Preview'])
    expect(wrapper.find('a').exists()).toBe(false)
    expect(sent.map((s) => s.url)).toEqual(['/api/tickets/r/CF-9/preview'])
  })

  test('the_button_starts_the_preview', async () => {
    const { wrapper, sent } = await shown(() => STOPPED)

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(sent.filter((s) => s.method !== 'GET').map((s) => [s.method, s.url])).toEqual([
      ['POST', '/api/tickets/r/CF-9/preview'],
    ])
  })

  test('a_running_preview_links_the_address_the_board_names_and_stops_on_stop', async () => {
    const { wrapper, sent } = await shown(() => RUNNING)

    const link = wrapper.get('a')
    await wrapper.findAll('button')[0]?.trigger('click')
    await flushPromises()

    expect(link.text()).toBe('Open preview')
    expect(link.attributes('href')).toBe('http://localhost:4321/')
    expect(wrapper.findAll('button').map((b) => b.text())).toEqual(['Stop'])
    expect(sent.filter((s) => s.method !== 'GET').map((s) => s.method)).toEqual(['DELETE'])
  })
})
