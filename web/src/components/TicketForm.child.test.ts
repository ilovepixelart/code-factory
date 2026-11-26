// @vitest-environment happy-dom

import { flushPromises } from '@vue/test-utils'
import { afterEach, expect, test, vi } from 'vitest'
import { form } from '../test/ticketForm'

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

// CF-817-R2: the ticket's footer offers New child ticket, opening the new ticket form for it.
test('the_ticket_offers_a_new_child_ticket', async () => {
  const { page } = await form()

  const button = page.findAll('footer button').find((b) => b.text().includes('New child ticket'))
  await button?.trigger('click')
  await flushPromises()

  // The sheet is portaled to the body, outside the ticket's form.
  const sheet = document.querySelector('body > [role="dialog"][data-state="open"]')
  const parent = document.querySelector<HTMLInputElement>('#child-parent')
  expect(sheet?.closest('form[aria-label="Edit ticket CF-1"]')).toBeNull()
  expect(sheet === null).toBe(false)
  expect(parent?.value ?? null).toBe('CF-1')
})
