import { afterEach, expect, test, vi } from 'vitest'
import { present } from '../../support/present'
import { act, readJson, Refused } from '@/lib/actions'

afterEach(() => {
  vi.unstubAllGlobals()
})

test('act_answers_a_change_and_throws_a_refusal', async () => {
  const fetch = vi
    .fn<typeof globalThis.fetch>()
    .mockResolvedValueOnce(Response.json({ notice: 'Archived CF-2', undo: 'abc' }))
    .mockResolvedValueOnce(Response.json({ detail: 'no such ticket' }, { status: 404 }))
    .mockResolvedValueOnce(new Response(null, { status: 502 }))
  vi.stubGlobal('fetch', fetch)

  const changed = await act('PATCH', '/api/tickets/sample/CF-2', { archived: 'true' })
  const refused = await act('DELETE', '/api/tickets/sample/CF-9').catch((e: unknown) => e)
  const broken = await act('POST', '/api/undo/x').catch((e: unknown) => e)

  expect(changed).toEqual({ notice: 'Archived CF-2', undo: 'abc' })
  expect(fetch.mock.calls[0]).toEqual([
    '/api/tickets/sample/CF-2',
    {
      method: 'PATCH',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: '{"archived":"true"}',
    },
  ])
  expect(fetch.mock.calls[1]?.[1]).toEqual({
    method: 'DELETE',
    headers: { Accept: 'application/json' },
    body: undefined,
  })
  expect(refused).toEqual(new Refused('no such ticket'))
  expect(broken).toEqual(new Refused('Refused (502)'))
})

test('only_the_request_helper_calls_fetch', () => {
  const sources = import.meta.glob<string>('/src/**/*.{ts,vue}', {
    query: '?raw',
    import: 'default',
    eager: true,
  })

  const calling = Object.entries(sources)
    .filter(([, text]) => /\bfetch\(/.test(text))
    .map(([path]) => path)

  expect(Object.keys(sources).length).toBeGreaterThan(50)
  expect(calling).toEqual(['/src/lib/actions.ts'])
})

test('act_carries_the_id_a_create_answers_and_ignores_one_that_is_not_text', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn<typeof globalThis.fetch>()
      .mockResolvedValueOnce(Response.json({ repository: 'sample', id: 'CF-6' }))
      .mockResolvedValueOnce(Response.json({ id: 6 })),
  )

  const created = await act('POST', '/api/tickets', {})
  const odd = await act('POST', '/api/tickets', {})

  expect([created, odd]).toEqual([
    { notice: '', undo: null, id: 'CF-6' },
    { notice: '', undo: null },
  ])
})

test('a_read_answers_the_value_or_null_when_refused', async () => {
  const answers = [
    new Response(JSON.stringify({ count: 2 }), { status: 200 }),
    new Response(JSON.stringify({ detail: 'no' }), { status: 404 }),
    new Response('busy', { status: 503 }),
  ]
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(present(answers.shift(), 'an answer'))),
  )

  expect(await readJson<{ count: number }>('/api/inbox/count')).toEqual({ count: 2 })
  expect(await readJson('/api/missing')).toBeNull()
  expect(await readJson('/api/busy')).toBeNull()
})

test('a_read_the_board_does_not_answer_throws', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))),
  )

  await expect(readJson('/api/inbox')).rejects.toThrow('Failed to fetch')
})
