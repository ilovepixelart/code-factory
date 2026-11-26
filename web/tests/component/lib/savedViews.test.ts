import { afterEach, expect, test, vi } from 'vitest'
import { useSavedViews } from '@/lib/savedViews'

afterEach(() => {
  vi.unstubAllGlobals()
})

test('deleting_a_view_names_it_in_the_path_and_sends_no_body', async () => {
  const sent: { method: string; url: string; body: unknown }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      sent.push({ method: init?.method ?? 'GET', url, body: init?.body ?? null })
      const answer = (init?.method ?? 'GET') === 'GET' ? [] : {}
      return Promise.resolve(new Response(JSON.stringify(answer), { status: 200 }))
    }),
  )

  await useSavedViews().remove('My bugs/today')

  expect(sent[0]).toEqual({ method: 'DELETE', url: '/api/views/My%20bugs%2Ftoday', body: null })
})
