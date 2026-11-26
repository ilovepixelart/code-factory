// @vitest-environment happy-dom
// The owner: /design opens at its top. A sample that takes focus on mount scrolls the page to it,
// so nothing on the page takes focus until the reader moves it.

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, test } from 'vitest'
import { memoryRouter } from '../test/board'
import DesignPage from './DesignPage.vue'

afterEach(() => {
  document.body.innerHTML = ''
})

test('nothing_on_the_design_page_takes_focus_on_mount', async () => {
  document.body.innerHTML = '<div id="app"></div>'
  const router = memoryRouter()
  await router.push('/design')
  const page = mount(DesignPage, { attachTo: '#app', global: { plugins: [router] } })
  await flushPromises()
  // A sample's own focus on mount waits a timer turn.
  await new Promise((resolve) => setTimeout(resolve, 10))

  expect(document.activeElement).toBe(document.body)
  page.unmount()
})
