// CF-314: Enter does nothing while the ticket form's action is pending, as its button does not
// (docs/ui.md: an action that is not idempotent disables its control while it runs).

import { flushPromises } from '@vue/test-utils'
import { afterEach, expect, test, vi } from 'vitest'
import { present } from '../../../support/present'
import { BASE, form, view } from '../../../support/ticketForm'

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

test('enter_twice_sends_one_answer', async () => {
  const { page, changes } = await form()
  const box = page.get('input[aria-label="Answer to Which colour?"]')
  await box.setValue('green')
  const typed = present(box.element.closest('form'), 'the answer form')

  typed.dispatchEvent(new Event('submit'))
  typed.dispatchEvent(new Event('submit'))
  await flushPromises()

  expect(changes).toEqual([`POST ${BASE}/answers`])
  page.unmount()
})

// CF-331: the ticket form's Open questions offer a question's choices, as the inbox does.
test('the_ticket_form_answers_a_question_from_its_choices', async () => {
  const choice = (text: string) => ({ text, recommended: false, reason: '', ticked: false })
  const asked = {
    ...(view as Record<string, unknown>),
    questions: [
      {
        document: 'uat.md',
        index: 0,
        text: 'Which page should the summary open on?',
        answer: '',
        several: false,
        choices: [
          { ...choice('Flow'), recommended: true, reason: 'it already holds the weekly numbers' },
          choice('Tickets'),
        ],
      },
      {
        document: 'uat.md',
        index: 1,
        text: 'Which notices should a run send?',
        answer: '',
        several: true,
        choices: [choice('When it ends'), choice('When its checks fail')],
      },
    ],
  }
  const { page, changes, bodies } = await form(asked)
  const items = page.findAll('ul[aria-label="Open questions"] > li')
  const one = present(items[0], 'the one question')
  const several = present(items[1], 'the several question')
  const offered = one
    .findAll('[data-slot="field-label"]')
    .map((card) => card.text().replace(/\s+/g, ' ').trim())

  await one.get('[data-answer]').trigger('click')
  await flushPromises()

  // As in the Inbox: the choices are cards, Other the last one, the recommended one picked to
  // start, and Answer sends the pick.
  expect(offered).toEqual([
    'Flow Recommended it already holds the weekly numbers',
    'Tickets',
    'Other',
  ])
  expect(several.findAll('[role="checkbox"]')).toHaveLength(3)
  expect(several.text()).toContain('Pick any')
  expect(
    one.find('input[aria-label="Other answer to Which page should the summary open on?"]').exists(),
  ).toBe(true)
  expect(changes).toEqual([`POST ${BASE}/answers`])
  expect(bodies).toEqual([
    {
      document: 'uat.md',
      index: 0,
      question: 'Which page should the summary open on?',
      choices: ['Flow'],
    },
  ])
  page.unmount()
})

// CF-438: the form is the one caller that changes an answer on purpose, and says so.
test('the_form_sends_its_edit_of_an_answered_question_as_a_replacement', async () => {
  const answered = {
    ...(view as Record<string, unknown>),
    questions: [
      {
        document: 'brd.md',
        index: 0,
        text: 'Which colour?',
        answer: 'Blue',
        several: false,
        choices: [],
      },
    ],
  }
  const { page, changes, bodies } = await form(answered)
  await page.get('input[aria-label="Answer to Which colour?"]').setValue('Red')

  await present(
    page.findAll('button').find((b) => b.text() === 'Update'),
    'Update',
  ).trigger('click')
  await flushPromises()

  expect(changes).toEqual([`POST ${BASE}/answers`])
  expect(bodies).toEqual([
    { document: 'brd.md', index: 0, question: 'Which colour?', answer: 'Red', replace: true },
  ])
  page.unmount()
})

// CF-1391: an answer shows the channel that gave it, and says only `answered` when none is recorded.
test('an_answer_shows_its_channel_or_says_answered_alone', async () => {
  const asked = (text: string, answered_by: string) => ({
    document: 'uat.md',
    index: 0,
    text,
    answer: 'Yes',
    answered_by,
    several: false,
    choices: [],
  })
  const { page } = await form({
    ...(view as Record<string, unknown>),
    questions: [asked('Via mcp?', 'mcp'), { ...asked('Old?', ''), index: 1 }],
  })
  const items = page.findAll('ul[aria-label="Open questions"] > li')

  expect(present(items[0], 'first').text()).toContain('answered via mcp')
  const second = present(items[1], 'second').text()
  expect(second).toContain('Yes answered')
  expect(second).not.toContain('answered via')
  expect(second).not.toContain('not known')
})

// The questions sit on the ticket's own surface, as its other sections do (docs/design.md: one
// surface level, no bordered box in a Sheet), so light control borders and muted text keep their
// contrast; Answer has an edge of its own.
test('the_open_questions_sit_on_the_ticket_surface_with_answer_as_the_primary', async () => {
  const choice = (text: string) => ({ text, recommended: false, reason: '', ticked: false })
  const asked = {
    ...(view as Record<string, unknown>),
    questions: [
      {
        document: 'uat.md',
        index: 0,
        text: 'Which page?',
        answer: '',
        several: false,
        choices: [choice('Flow'), choice('Tickets')],
      },
    ],
  }
  const { page } = await form(asked)
  const section = page.get('section[aria-labelledby="questions-heading"]')
  // Answer is the page's primary button, as on the Inbox's next question.
  expect(section.classes()).toEqual([])
  expect(section.get('[data-answer]').attributes('data-variant')).toBe('default')
  page.unmount()
})
