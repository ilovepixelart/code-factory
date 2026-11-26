// @vitest-environment happy-dom
// CF-1272: the requests a button and a command menu entry both send.

import { afterEach, expect, test, vi } from 'vitest'
import { answer, stubFetch } from '../test/board'
import { setArchived, startAgent, ticketPath } from './ticketActions'

afterEach(() => vi.unstubAllGlobals())

test('a_ticket_path_escapes_its_parts', () => {
  expect(ticketPath('my repo', 'CF-1')).toBe('/api/tickets/my%20repo/CF-1')
})

test('start_agent_posts_the_runs_route_with_accept_edits_and_continuation', async () => {
  const sent = stubFetch(() => answer({ notice: '', undo: null }))

  await startAgent('/api/tickets/s/CF-1')

  expect(sent).toEqual([
    {
      method: 'POST',
      url: '/api/tickets/s/CF-1/runs',
      body: { permissions: 'bypassPermissions', loop: true },
    },
  ])
})

test('archiving_sends_true_and_restoring_sends_an_empty_value_beside_the_fields', async () => {
  const sent = stubFetch(() => answer({ notice: '', undo: null }))

  await setArchived('/api/tickets/s/CF-1', true)
  await setArchived('/api/tickets/s/CF-1', false, { title: 'T' })

  expect(sent.map((s) => s.body)).toEqual([{ archived: 'true' }, { title: 'T', archived: '' }])
})
