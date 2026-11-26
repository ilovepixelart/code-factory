// @vitest-environment happy-dom
// An address the app has no page for: the header's h1 reads Not found, so the card says what is
// missing instead of repeating it, and offers Tickets.

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, test } from 'vitest'
import { memoryRouter } from '../test/board'
import NotFound from './NotFound.vue'

afterEach(() => {
  document.body.innerHTML = ''
})

test('the_card_says_nothing_is_at_the_address_without_repeating_the_page_title', async () => {
  const router = memoryRouter([{ path: '/:rest(.*)*', component: NotFound }])
  await router.push('/no-such-page')
  const view = mount(NotFound, { global: { plugins: [router] } })
  await flushPromises()

  expect([view.get('h2').text(), view.get('section p').text()]).toEqual([
    'Nothing at this address',
    'There is no page at /no-such-page.',
  ])
  view.unmount()
})
