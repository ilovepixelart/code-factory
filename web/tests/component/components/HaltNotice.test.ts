// CF-364: while every agent is stopped the board says since when, and Resume agents starts them
// again; the notice reads the halt again whenever the board changes.

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { clear } from '@/lib/notice'
import { answer, goldenBoard, spiedBoard, stubFetch } from '../../support/board'
import HaltNotice from '@/components/HaltNotice.vue'

// 1790000000 is 20717 days and 51200 seconds after the epoch: 14:13:20 UTC.
const HALTED_AT = 1_790_000_000
let zone: string | undefined

async function notice(
  haltedAt: () => number | null,
  resume: () => Response | Promise<Response> = () => answer({ notice: '' }),
) {
  const sent = stubFetch((url) =>
    url === '/api/agents/resume' ? resume() : answer({ halted_at: haltedAt() }),
  )
  const { live, provide } = spiedBoard(goldenBoard())
  const wrapper = mount(HaltNotice, { global: { provide } })
  await flushPromises()
  return { wrapper, live, sent }
}

beforeEach(() => {
  zone = process.env.TZ
  process.env.TZ = 'UTC'
})

afterEach(() => {
  process.env.TZ = zone
  vi.unstubAllGlobals()
  clear()
})

describe('the halt notice', () => {
  test('nothing_shows_while_the_agents_run', async () => {
    const { wrapper } = await notice(() => null)

    expect(wrapper.find('[role="region"]').exists()).toBe(false)
  })

  test('a_halt_shows_when_the_agents_stopped', async () => {
    const { wrapper } = await notice(() => HALTED_AT)

    expect(wrapper.get('[role="region"]').attributes('aria-labelledby')).toBe('halt-notice-heading')
    expect(wrapper.get('#halt-notice-heading').text()).toBe('Agents are stopped')
    expect(wrapper.text()).toContain('Stopped at 14:13. Nothing starts until you resume.')
  })

  test('resume_starts_the_agents_and_reads_the_halt_and_the_board_again', async () => {
    let halted: number | null = HALTED_AT
    const { wrapper, live, sent } = await notice(
      () => halted,
      () => {
        halted = null
        return answer({ notice: 'Agents resumed' })
      },
    )

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(sent.map((s) => `${s.method} ${s.url}`)).toEqual([
      'GET /api/agents',
      'POST /api/agents/resume',
      'GET /api/agents',
    ])
    expect(live.refresh).toHaveBeenCalledWith({ force: true })
    expect(wrapper.find('[role="region"]').exists()).toBe(false)
  })

  test('resume_is_disabled_while_it_is_sent', async () => {
    let reply: (response: Response) => void = () => undefined
    const { wrapper } = await notice(
      () => HALTED_AT,
      () => new Promise<Response>((resolve) => (reply = resolve)),
    )

    await wrapper.get('button').trigger('click')
    const during = wrapper.get('button').attributes('disabled')
    reply(answer({ notice: '' }))
    await flushPromises()

    expect(during).toBeDefined()
    expect(wrapper.get('button').attributes('disabled')).toBeUndefined()
  })

  test('a_board_change_reads_the_halt_again', async () => {
    let halted: number | null = null
    const { wrapper, live } = await notice(() => halted)

    halted = HALTED_AT
    live.board.value = { ...goldenBoard() }
    await flushPromises()

    expect(wrapper.find('[role="region"]').exists()).toBe(true)
  })

  test('a_read_the_board_refuses_keeps_what_the_notice_showed', async () => {
    let refuse = false
    const sent = stubFetch(() =>
      refuse ? answer({ detail: 'no' }, 500) : answer({ halted_at: HALTED_AT }),
    )
    const { live, provide } = spiedBoard(goldenBoard())
    const wrapper = mount(HaltNotice, { global: { provide } })
    await flushPromises()

    refuse = true
    live.board.value = { ...goldenBoard() }
    await flushPromises()

    expect(sent).toHaveLength(2)
    expect(wrapper.find('[role="region"]').exists()).toBe(true)
  })

  test('an_older_read_answering_last_never_brings_back_a_halt_the_newer_read_found_resumed', async () => {
    const held: ((response: Response) => void)[] = []
    let asked = 0
    stubFetch(() => {
      asked += 1
      return asked === 1
        ? new Promise<Response>((resolve) => held.push(resolve))
        : answer({ halted_at: null })
    })
    const { live, provide } = spiedBoard(goldenBoard())
    const wrapper = mount(HaltNotice, { global: { provide } })
    await flushPromises()

    live.board.value = { ...goldenBoard() }
    await flushPromises()
    for (const reply of held) reply(answer({ halted_at: HALTED_AT }))
    await flushPromises()

    expect(asked).toBe(2)
    expect(wrapper.find('[role="region"]').exists()).toBe(false)
  })
})
