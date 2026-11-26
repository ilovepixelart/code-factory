import { afterEach, expect, test, vi } from 'vitest'
import { announce, clear, failed, notice, useAction } from '@/lib/notice'

afterEach(() => {
  vi.unstubAllGlobals()
  clear()
})

test('an_action_announces_its_answer_or_keeps_its_refusal', async () => {
  let answer: (response: Response) => void = () => undefined
  const fetch = vi
    .fn<typeof globalThis.fetch>()
    .mockReturnValueOnce(new Promise((resolve) => (answer = resolve)))
    .mockResolvedValueOnce(
      Response.json({ detail: 'agent qwen uses connection local' }, { status: 409 }),
    )
    .mockResolvedValueOnce(Response.json({ notice: '', undo: null }))
  vi.stubGlobal('fetch', fetch)
  const action = useAction()
  const done = vi.fn()

  const saving = action.send('PATCH', '/api/connections/local', { base_url: 'h' }, done)
  expect(action.busy.value).toBe(true)
  expect(done).not.toHaveBeenCalled()
  answer(Response.json({ notice: 'Saved local', undo: 'u1' }))
  await saving

  expect({ ...notice }).toEqual({ text: 'Saved local', undo: 'u1', error: false, follow: null })
  expect(done).toHaveBeenCalledTimes(1)
  expect(action.busy.value).toBe(false)
  expect(action.error.value).toBe('')

  await action.send('DELETE', '/api/connections/local', undefined, done)

  expect(action.error.value).toBe('agent qwen uses connection local')
  expect(done).toHaveBeenCalledTimes(1)
  expect(action.busy.value).toBe(false)

  const next = action.send('POST', '/api/connections', {}, done)
  expect(action.error.value).toBe('')
  await next
  expect(done).toHaveBeenCalledTimes(2)
})

test('an_answer_with_no_notice_clears_the_earlier_one', () => {
  failed('CF-2 needs a branch before Build')
  expect(notice.text).toBe('CF-2 needs a branch before Build')

  announce({ notice: '', undo: null })

  expect({ ...notice }).toEqual({ text: '', undo: null, error: false, follow: null })
})
