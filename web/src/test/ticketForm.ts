// The ticket form mounted whole over a stubbed `fetch`, as its section tests drive it.

import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { vi } from 'vitest'
import TicketForm from '../components/TicketForm.vue'
import { golden, memoryRouter, provideBoard } from './board'

const views = golden('tickets.golden.json') as { view: unknown }[]
export const view = views[0]?.view

export const BASE = '/api/tickets/sample/CF-1'

/** The form over a server that answers reads at once and holds every change. `links` renders what
 *  a RouterLink holds, which the default stub leaves out; `reads` answers a read whose address ends
 *  in its key, any other read the ticket; `page` false mounts it as the panel's form. */
export async function form(
  shown: unknown = view,
  links = false,
  reads: Record<string, unknown> = {},
  page = true,
) {
  const changes: string[] = []
  const bodies: unknown[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      if (method === 'GET') {
        const read = Object.keys(reads).find((end) => url.endsWith(end))
        const body = read === undefined ? shown : reads[read]
        return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }))
      }
      changes.push(`${method} ${url}`)
      bodies.push(typeof init?.body === 'string' ? JSON.parse(init.body) : null)
      return new Promise<Response>(() => undefined)
    }),
  )
  // A fresh element per form: emptying the body would pull the portal anchors of a form mounted
  // earlier in the test out from under it.
  const app = document.body.appendChild(document.createElement('div'))
  const router = memoryRouter([{ path: '/', component: { template: '<div />' } }])
  const mounted = mount(TicketForm, {
    attachTo: app,
    props: { repository: 'sample', id: 'CF-1', page },
    global: {
      plugins: [router],
      provide: provideBoard(),
      stubs: { RouterLink: links ? RouterLinkStub : true, TicketChanges: true },
    },
  })
  await flushPromises()
  return { page: mounted, changes, bodies }
}
