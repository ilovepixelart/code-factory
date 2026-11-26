// CF-1200-R9: a ui ticket's screens: its pages, the latest capture's state and its images.

import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import { view } from '../../../support/ticketForm'
import TicketScreens from '@/components/ticket/TicketScreens.vue'

function screens(ticket: Record<string, unknown>, capture: unknown) {
  const props = {
    id: 'CF-1',
    repository: 'sample',
    view: { ...(view as object), ticket, status: { conflict: null, capture } },
  }
  return mount(TicketScreens, { props: props as never })
}

test('ticket_screens_show_capture_and_pages', () => {
  const page = screens(
    { pages: '/flow, /inbox' },
    { tree: 't2', images: ['a.png'], state: 'sent_back', reason: 'Too dark' },
  )

  expect(page.text()).toContain('Pages: /flow, /inbox')
  expect(page.find('[data-capture]').text().replace(/\s+/g, ' ')).toBe(
    'Tree t2 · sent back: Too dark',
  )
  expect(page.find('a').attributes('href')).toBe('/api/captures/sample/CF-1/t2/a.png')
})

test('ticket_screens_say_when_nothing_was_captured', () => {
  expect(screens({}, null).text()).toContain('No capture yet')
})

test('each_image_is_an_attachment_named_for_it_with_the_capture_state', () => {
  const page = screens(
    {},
    { tree: 't3', images: ['flow-light.png', 'flow-dark.png'], state: 'approved', by: 'alex' },
  )
  const attachments = page.findAll('[data-slot="attachment"]')

  expect(attachments.map((a) => a.get('[data-slot="attachment-title"]').text())).toEqual([
    'flow-light.png',
    'flow-dark.png',
  ])
  expect(attachments.map((a) => a.get('[data-slot="attachment-description"]').text())).toEqual([
    'approved by alex',
    'approved by alex',
  ])
  expect(attachments.map((a) => a.attributes('data-state'))).toEqual(['done', 'done'])
})

test('an_image_shows_at_the_captures_16_by_9_and_its_card_opens_the_full_image', () => {
  const page = screens({}, { tree: 't3', images: ['flow-light.png'], state: 'waiting' })
  const attachment = page.get('[data-slot="attachment"]')
  const open = attachment.get('[data-slot="attachment-trigger"]')

  expect(attachment.get('[data-reka-aspect-ratio-wrapper]').attributes('style')).toContain(
    'padding-bottom: 56.25%',
  )
  expect(attachment.get('img').attributes('src')).toBe(
    '/api/captures/sample/CF-1/t3/flow-light.png',
  )
  expect([open.element.tagName, open.attributes('href'), open.attributes('aria-label')]).toEqual([
    'A',
    '/api/captures/sample/CF-1/t3/flow-light.png',
    'Open flow-light.png',
  ])
})

test('the_images_of_a_capture_sent_back_are_in_the_error_state_with_the_reason', () => {
  const page = screens(
    {},
    { tree: 't2', images: ['a.png'], state: 'sent_back', reason: 'Too dark' },
  )
  const attachment = page.get('[data-slot="attachment"]')

  expect(attachment.attributes('data-state')).toBe('error')
  expect(attachment.get('[data-slot="attachment-description"]').text()).toBe('sent back: Too dark')
})
