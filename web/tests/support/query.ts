// A composable that reads through TanStack Query, run as a component's setup would run it: inside
// an app that provides a fresh client, in a scope the test stops as a page is left.

import { VueQueryPlugin, type QueryClient } from '@tanstack/vue-query'
import { createApp, effectScope } from 'vue'
import { createQueryClient } from '@/lib/queries'
import { present } from './present'

export interface InQuery<T> {
  value: T
  client: QueryClient
  /** Run `more` in the same app and a scope of its own, as a page opened beside the first. */
  beside: (more: () => void) => () => void
  stop: () => void
}

export function inQuery<T>(setup: () => T): InQuery<T> {
  const client = createQueryClient()
  const app = createApp({ render: () => null }).use(VueQueryPlugin, { queryClient: client })
  const scope = effectScope()
  const value = present(
    app.runWithContext(() => scope.run(setup)),
    'the composable',
  )
  return {
    value,
    client,
    beside(more) {
      const page = effectScope()
      app.runWithContext(() => page.run(more))
      return () => {
        page.stop()
      }
    },
    stop() {
      scope.stop()
      client.clear()
    },
  }
}
