// Failures no page catches: shown in the page's notice, never only logged (CF-542).

import type { App } from 'vue'
import { failed } from './notice'

function textOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

/** Show in the page's notice an error Vue catches no page for, and a rejection nothing handles. */
export function watchFailures(app: App, page: Pick<Window, 'addEventListener'> = window): void {
  app.config.errorHandler = (error) => {
    failed(textOf(error))
  }
  page.addEventListener('unhandledrejection', (event) => {
    failed(textOf(event.reason))
  })
}
