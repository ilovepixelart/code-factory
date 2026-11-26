// CF-212 acceptance flows: the Inbox and the sidebar's count on the Vue board,
// served by the server over the writes sample state.

import { TIMEOUT, expect, seedInbox, test } from './fixtures'

test('e2e_the_inbox_answers_a_question', async ({ served, writesBoard }) => {
  seedInbox(served, { ticket: 'CF-1', question: { text: 'Which size?' } })
  await writesBoard.goto(`${served.url}/inbox`)
  const questions = writesBoard.getByRole('region', { name: 'Questions' })
  const box = questions.getByLabel('Answer to Which size?')
  await box.fill('large')
  await questions.getByRole('button', { name: 'Answer' }).click()
  await questions.waitFor({ state: 'detached', timeout: TIMEOUT })

  const ticket = await served.api('GET', '/api/tickets/sample/CF-1')
  expect(ticket.json).toMatchObject({ questions: [{ text: 'Which size?', answer: 'large' }] })
})

// CF-1389: an answer is recorded only for the question the owner saw.
test('e2e_an_answer_to_a_question_that_changed_shows_the_new_text_and_records_nothing', async ({
  served,
  writesBoard,
}) => {
  seedInbox(served, { ticket: 'CF-1', question: { text: 'Which size?' } })
  await writesBoard.goto(`${served.url}/inbox`)
  const questions = writesBoard.getByRole('region', { name: 'Questions' })
  const box = questions.getByLabel('Answer to Which size?')
  await box.fill('large')
  seedInbox(served, {
    ticket: 'CF-1',
    rewrite: { before: 'Which size?', after: 'Which size should we ship?' },
  })

  await questions.getByRole('button', { name: 'Answer' }).click()

  await expect(
    questions.getByText('the question changed: it now asks Which size should we ship?'),
  ).toBeVisible({
    timeout: TIMEOUT,
  })
  await expect(questions.getByText('Which size should we ship?', { exact: true })).toBeVisible()
  const ticket = await served.api('GET', '/api/tickets/sample/CF-1')
  expect(ticket.json).toMatchObject({
    questions: [{ text: 'Which size should we ship?', answer: '' }],
  })
})

test('e2e_the_sidebar_counts_what_waits', async ({ served, writesBoard }) => {
  seedInbox(served, { ticket: 'CF-1', question: { text: 'Which size?' } })
  const badge = writesBoard
    .getByRole('navigation', { name: 'Pages' })
    .getByRole('listitem')
    .filter({ has: writesBoard.getByRole('link', { name: /^Inbox/ }) })
    .getByText(/^\d+$/)
  await badge.waitFor({ timeout: TIMEOUT })

  await expect(badge).toHaveText('1')
  await expect(writesBoard).toHaveTitle(/^\(1\) /)
})
