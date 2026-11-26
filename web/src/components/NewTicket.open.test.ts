// @vitest-environment happy-dom
// The new ticket dialog applies only the latest answer of its reads: an earlier open's repositories
// never override a later open's preset, an old template never lands in a form opened since, and a
// template read the board does not answer leaves the description as it is, silently.

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { INLINE } from '../test/overlay'
import { afterEach, expect, test, vi } from 'vitest'
import { clear, notice } from '../lib/notice'
import { answer, spiedBoard, stubFetch } from '../test/board'
import NewTicket from './NewTicket.vue'

interface Preset {
  repository?: string
  parent?: string
}
const REPOSITORIES = ['sample', 'second']

function mounted(): { wrapper: VueWrapper; open: (preset?: Preset) => Promise<void> } {
  const { provide } = spiedBoard()
  const wrapper = mount(NewTicket, { global: { provide, stubs: INLINE }, attachTo: document.body })
  const open = (preset?: Preset) =>
    (wrapper.vm as unknown as { open: (p?: Preset) => Promise<void> }).open(preset)
  return { wrapper, open }
}

const valueOf = (wrapper: VueWrapper, selector: string) =>
  (wrapper.get(selector).element as HTMLInputElement).value

/** The unhandled rejections raised while `run` works, taken from the test runner's own listeners
 *  for that time. */
async function rejectionsDuring(run: () => Promise<void>): Promise<unknown[]> {
  const saved = process.listeners('unhandledRejection')
  const seen: unknown[] = []
  process.removeAllListeners('unhandledRejection')
  process.on('unhandledRejection', (reason) => seen.push(reason))
  try {
    await run()
    await new Promise((resolve) => setTimeout(resolve, 0))
  } finally {
    process.removeAllListeners('unhandledRejection')
    for (const listener of saved) process.on('unhandledRejection', listener)
  }
  return seen
}

afterEach(() => {
  vi.unstubAllGlobals()
  clear()
  document.body.innerHTML = ''
})

test('an_earlier_open_answered_last_never_overrides_the_later_opens_repository', async () => {
  let release: (response: Response) => void = () => undefined
  let listed = 0
  stubFetch((url) => {
    if (url === '/api/repositories') {
      listed += 1
      return listed === 1
        ? new Promise<Response>((resolve) => (release = resolve))
        : answer(REPOSITORIES)
    }
    return answer({ text: '' })
  })
  const { wrapper, open } = mounted()

  const first = open({ repository: 'second' })
  await open({ repository: 'sample', parent: 'CF-7' })
  release(answer(REPOSITORIES))
  await first
  await flushPromises()

  expect([valueOf(wrapper, '#new-repository'), valueOf(wrapper, '#new-parent')]).toStrictEqual([
    'sample',
    'CF-7',
  ])
})

test('a_template_read_answered_after_the_form_was_opened_again_is_dropped', async () => {
  let release: (response: Response) => void = () => undefined
  let templates = 0
  stubFetch((url) => {
    if (url === '/api/repositories') return answer(REPOSITORIES)
    templates += 1
    return templates === 1
      ? new Promise<Response>((resolve) => (release = resolve))
      : answer({ text: '## New\n' })
  })
  const { wrapper, open } = mounted()

  await open()
  await flushPromises()
  await open()
  await flushPromises()
  release(answer({ text: '## Old\n' }))
  await flushPromises()

  expect(templates).toBe(2)
  expect(valueOf(wrapper, '#new-description')).toBe('## New\n')
})

test('a_template_read_the_board_does_not_answer_leaves_the_description_and_says_nothing', async () => {
  stubFetch((url) =>
    url === '/api/repositories'
      ? answer(REPOSITORIES)
      : Promise.reject(new TypeError('Failed to fetch')),
  )
  const { wrapper, open } = mounted()

  const rejected = await rejectionsDuring(async () => {
    await open()
    await flushPromises()
  })

  expect(rejected).toStrictEqual([])
  expect(notice.text).toBe('')
  expect(valueOf(wrapper, '#new-description')).toBe('')
})
