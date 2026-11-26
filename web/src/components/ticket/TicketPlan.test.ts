// @vitest-environment happy-dom

import { afterEach, describe, expect, test, vi } from 'vitest'
import { form, view } from '../../test/ticketForm'

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

describe('the plan', () => {
  const planned = {
    ...(view as object),
    plan: {
      items: [
        { text: 'Write the test', done: true },
        { text: 'Make it pass', done: false },
        { text: 'Update the docs', done: false },
      ],
      done: 1,
      total: 3,
    },
  }

  // CF-1219-R4: the page lists the plan's items, each saying whether it is done, with the count
  // and the bar.
  test('the_page_shows_the_plan_with_its_ticks_and_count', async () => {
    const { page } = await form(planned)

    const items = page.findAll('[aria-label="Plan items"] li').map((i) => i.text())
    const bar = page.get('[role="progressbar"][aria-label="Plan progress"]')

    expect(items).toEqual(['Write the test, done', 'Make it pass, next', 'Update the docs, to do'])
    expect(page.find('#plan-heading').text()).toContain('1 of 3 done')
    expect([bar.attributes('aria-valuenow'), bar.attributes('aria-valuemax')]).toEqual([
      '33',
      '100',
    ])
  })

  // CF-1219-R4: the plan comes before the description.
  test('the_plan_precedes_the_description', async () => {
    const { page } = await form(planned)

    const order = page.html()

    expect(order.indexOf('id="plan-heading"')).toBeGreaterThan(-1)
    expect(order.indexOf('id="plan-heading"')).toBeLessThan(
      order.indexOf('id="description-heading"'),
    )
  })

  // CF-1219-R4: a ticket without a plan shows no Plan section.
  test('a_ticket_without_a_plan_shows_no_plan', async () => {
    const { page } = await form({ ...(view as object), plan: null })

    expect(page.find('#plan-heading').exists()).toBe(false)
  })
})
