import { afterEach, expect, test } from 'vitest'
import { createApp } from 'vue'
import { watchFailures } from '@/lib/failures'
import { clear, notice } from '@/lib/notice'

afterEach(() => {
  clear()
})

/** An app and a page with the failures watched. */
function watched() {
  const app = createApp({})
  const page = new EventTarget() as unknown as Window
  watchFailures(app, page)
  return { app, page }
}

test('an_error_no_page_catches_shows_in_the_notice', () => {
  const { app } = watched()

  app.config.errorHandler?.(new Error('the agents list did not parse'), null, 'render')

  expect(notice).toMatchObject({ text: 'the agents list did not parse', error: true })
})

test('a_rejection_nothing_handles_shows_in_the_notice', () => {
  const { page } = watched()
  const event = Object.assign(new Event('unhandledrejection'), {
    reason: 'the board did not answer',
  })

  page.dispatchEvent(event)

  expect(notice).toMatchObject({ text: 'the board did not answer', error: true })
})
