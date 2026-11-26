// @vitest-environment happy-dom
// CF-338: desktop notifications as docs/ui.md (The kanban) sets them, asserted on the request to
// the browser to show one, not on the system's popup.

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { notifying, setNotifying, useAttention } from './attention'

const POLL_MS = 5000

let shown: { title: string; body: string }[] = []
let asked = 0
let counts: { count: number; latest: string }[] = []

class FakeNotification {
  static permission: NotificationPermission = 'granted'
  static requestPermission(): Promise<NotificationPermission> {
    asked += 1
    return Promise.resolve(FakeNotification.permission)
  }
  onclick: (() => void) | null = null
  constructor(title: string, options: { body: string }) {
    shown.push({ title, body: options.body })
  }
}

const Host = defineComponent({
  setup() {
    useAttention()
    return () => h('div')
  },
})

async function host() {
  const view = mount(Host, { attachTo: document.body })
  await flushPromises()
  return view
}

beforeEach(() => {
  shown = []
  asked = 0
  counts = []
  FakeNotification.permission = 'granted'
  vi.useFakeTimers()
  vi.stubGlobal('Notification', FakeNotification)
  vi.stubGlobal(
    'fetch',
    vi.fn(() => {
      const next = counts.length > 1 ? counts.shift() : counts[0]
      return Promise.resolve(new Response(JSON.stringify(next), { status: 200 }))
    }),
  )
  Object.defineProperty(document, 'hidden', { configurable: true, get: () => true })
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  localStorage.clear()
  document.body.innerHTML = ''
})

describe('desktop notifications', () => {
  // CF-439-R3: a browser without the Notification API: switching on asks nothing and stays off.
  test('switching_notifications_without_the_api_stays_off', async () => {
    vi.unstubAllGlobals()
    const held = Reflect.getOwnPropertyDescriptor(window, 'Notification')
    Reflect.deleteProperty(window, 'Notification')
    try {
      await setNotifying(true)
      expect(notifying()).toBe(false)
    } finally {
      if (held) Reflect.defineProperty(window, 'Notification', held)
    }
  })

  test('a_notification_says_what_arrived_when_the_inbox_count_grows_while_hidden', async () => {
    counts = [
      { count: 1, latest: 'CF-1 asks: Which colour?' },
      { count: 2, latest: 'CF-2 asks: Which size?' },
    ]
    const view = await host()
    const first = [...shown]

    await vi.advanceTimersByTimeAsync(POLL_MS)

    expect(first).toEqual([])
    expect(shown).toEqual([{ title: '2 wait on you', body: 'CF-2 asks: Which size?' }])
    view.unmount()
  })

  test('the_inbox_count_is_polled_while_the_tab_is_hidden', async () => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
    counts = [
      { count: 1, latest: 'CF-1 asks: Which colour?' },
      { count: 2, latest: 'CF-2 asks: Which size?' },
    ]
    const view = await host()

    await vi.advanceTimersByTimeAsync(POLL_MS)

    expect(shown).toEqual([{ title: '2 wait on you', body: 'CF-2 asks: Which size?' }])
    view.unmount()
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
  })

  test('the_first_click_or_key_press_asks_the_browser_for_permission_once', async () => {
    FakeNotification.permission = 'default'
    counts = [{ count: 0, latest: '' }]
    const view = await host()
    const before = asked

    document.body.click()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'a' }))
    document.body.click()

    expect(before).toBe(0)
    expect(asked).toBe(1)
    view.unmount()
  })

  test('notifications_switched_off_on_the_inbox_page_neither_ask_nor_fire', async () => {
    localStorage.setItem('codeFactoryNotify', 'off')
    FakeNotification.permission = 'default'
    counts = [{ count: 1, latest: 'CF-1 asks' }]
    const quiet = await host()
    document.body.click()
    quiet.unmount()
    FakeNotification.permission = 'granted'
    counts = [
      { count: 1, latest: 'CF-1 asks' },
      { count: 2, latest: 'CF-2 asks' },
    ]
    const view = await host()

    await vi.advanceTimersByTimeAsync(POLL_MS)

    expect(asked).toBe(0)
    expect(shown).toEqual([])
    view.unmount()
  })
})
