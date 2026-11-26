// Every section of the ticket form is titled the same way: one heading component, no icon.

import { afterEach, expect, test, vi } from 'vitest'
import { form, view } from '../../../support/ticketForm'

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

test('every_section_of_the_ticket_form_has_the_same_heading', async () => {
  const question = {
    text: 'Which one?',
    document: 'spec',
    index: 0,
    several: false,
    choices: [],
    answer: '',
  }
  const { page } = await form({ ...(view as object), questions: [question] })
  const headings = page.findAll('section > h2, section > div > h2')

  expect(headings.length).toBeGreaterThan(5)
  expect(
    headings
      .filter((h) => h.attributes('data-slot') !== 'section-heading' || h.find('svg').exists())
      .map((h) => h.text()),
  ).toEqual([])
  page.unmount()
})
