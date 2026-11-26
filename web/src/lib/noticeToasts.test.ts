// @vitest-environment happy-dom
// The page's notice and the reload offer are vue-sonner toasts: what a change did with its Undo,
// a refusal, and that the board was updated.

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, expect, test, vi } from 'vitest'
import { Toasts } from '../test/toasts'
import { build, resetBuild, UPDATED } from './build'
import { announce, clear, failed } from './notice'
import { bottomLift } from './noticeToasts'

let view: VueWrapper | undefined

afterEach(() => {
  view?.unmount()
  clear()
  resetBuild()
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

const toasts = (): HTMLElement[] => [
  ...document.querySelectorAll<HTMLElement>('[data-sonner-toast]:not([data-removed="true"])'),
]
const words = (): string[] =>
  toasts().map((t) => t.querySelector('[data-title]')?.textContent ?? '')
// vue-sonner draws a toast a tick after it is made and takes one down a frame after it is dismissed.
const settle = async (): Promise<void> => {
  await flushPromises()
  await new Promise((resolve) => requestAnimationFrame(resolve))
  await flushPromises()
}

async function shown(): Promise<void> {
  view = mount(Toasts, { attachTo: document.body })
  await settle()
}

test('a_change_shows_its_notice_with_an_undo_that_takes_it_back', async () => {
  const fetch = vi.fn(() => Promise.resolve(Response.json({ notice: 'Restored CF-2', undo: null })))
  vi.stubGlobal('fetch', fetch)
  await shown()

  announce({ notice: 'Archived CF-2', undo: 'u-7' })
  await settle()
  expect(words()).toEqual(['Archived CF-2'])
  const undo = [...document.querySelectorAll('button')].find((b) => b.textContent === 'Undo')
  undo?.click()
  await settle()

  expect(fetch).toHaveBeenCalledWith('/api/undo/u-7', expect.objectContaining({ method: 'POST' }))
  expect(words()).toEqual(['Restored CF-2'])
})

test('a_refusal_is_an_error_toast_without_undo', async () => {
  await shown()

  failed('The board did not answer; try again.')
  await settle()

  expect(words()).toEqual(['The board did not answer; try again.'])
  expect(toasts()[0]?.dataset.type).toBe('error')
  expect([...document.querySelectorAll('button')].map((b) => b.textContent)).not.toContain('Undo')
})

test('a_cleared_notice_takes_its_toast_down', async () => {
  await shown()
  announce({ notice: 'Saved writer', undo: null })
  await settle()

  clear()
  await settle()

  expect(words()).toEqual([])
})

test('a_notice_shown_right_after_a_clear_stays_up', async () => {
  await shown()
  announce({ notice: 'Archived CF-2', undo: null })
  await settle()

  clear()
  await flushPromises()
  announce({ notice: 'Archived CF-3', undo: null })
  await settle()
  await settle()

  expect(words()).toEqual(['Archived CF-3'])
})

test('a_newer_build_offers_a_reload', async () => {
  await shown()

  build.stale = true
  await settle()

  expect(words()).toEqual([UPDATED])
  expect([...document.querySelectorAll('button')].map((b) => b.textContent)).toContain('Reload')
})

// A toast covered the agents-stopped bar: every bar that holds the bottom edge lifts the toasts
// above the highest of them, not only the bulk bar.
test('the_toasts_sit_above_the_highest_bar_holding_the_bottom_edge', () => {
  const bar = (top: number): void => {
    const element = document.createElement('div')
    element.dataset.holdsBottom = ''
    element.getBoundingClientRect = () => ({ top }) as DOMRect
    document.body.append(element)
  }

  const none = bottomLift(900)
  bar(840)
  bar(780)

  expect([none, bottomLift(900)]).toEqual([null, 900 - 780 + 8])
})
