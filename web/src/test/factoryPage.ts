// What the Factory pages' tests share: the page mounted at an address with the answers of
// `test/factory.ts`, and readers of what it drew.

import { ANALYTICS_TABS } from '../lib/analytics'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { vi } from 'vitest'
import type { Component } from 'vue'
import { answer, memoryRouter, stubFetch, type Sent } from './board'
import { present } from './present'

const PAGES = ANALYTICS_TABS.map(([path]) => path)

/** Mount `page` at `address` with `reply` answering every read; the clock stands at Nov 10 2026, 15:00 UTC. */
export async function pageAt(
  page: Component,
  address: string,
  reply: (url: string) => Response | Promise<Response>,
): Promise<{ wrapper: VueWrapper; sent: Sent[]; router: ReturnType<typeof memoryRouter> }> {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-11-10T15:00:00Z'))
  document.body.innerHTML = '<div id="header-controls"></div><div id="app"></div>'
  const sent = stubFetch(reply)
  const router = memoryRouter([
    ...PAGES.map((path) => ({ path, component: page })),
    { path: '/:rest(.*)*', component: { render: () => null } },
  ])
  await router.push(address)
  const wrapper = mount(page, { attachTo: '#app', global: { plugins: [router] } })
  await flushPromises()
  return { wrapper, sent, router }
}

/** The JSON answer of a read. */
export const json = answer

/** The text of an element with its whitespace collapsed, or null when there is none. */
export const words = (element: Element | null | undefined): string | null =>
  element ? element.textContent.replace(/\s+/g, ' ').trim() : null

/** A tile's value and the line under it. */
export const tile = (name: string) =>
  document.querySelector(`[aria-label="${name}"] [data-slot="card-title"]`)
export const tileText = (name: string): string | null => words(tile(name))
export const tileNote = (name: string): string | null =>
  words(document.querySelector(`[aria-label="${name}"] [data-slot="card-footer"]`))

/** The section under a heading. */
export const section = (heading: string): Element | null =>
  document.getElementById(heading)?.closest('section') ?? null

/** The cells of each body row of the table in a section. */
export const rows = (heading: string): (string | null)[][] =>
  [...(section(heading)?.querySelectorAll('tbody tr') ?? [])].map((row) =>
    [...row.querySelectorAll('td')].map((cell) => words(cell)),
  )

/** The links of a navigation by its label: their words, addresses and which one is current. */
export const links = (label: string) =>
  [...document.querySelectorAll(`nav[aria-label="${label}"] a`)].map((a) => ({
    text: words(a),
    href: a.getAttribute('href'),
    current: a.getAttribute('aria-current'),
  }))

/** Press the Read again button of a page whose read failed. */
export function readAgain(): void {
  present(document.querySelector<HTMLElement>('[data-read-again]'), 'the Read again button').click()
}
