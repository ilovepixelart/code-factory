// CF-1200-R10, R11: a run says which memory it received, what recall left out, and its context.

import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import { memoryRouter } from '../../../support/board'
import type { RunMemory } from '@/lib/ticket'
import RunMemoryLine from '@/components/ticket/RunMemory.vue'

const NOW = 1_794_312_000

function shown(props: { memory: RunMemory | null; contextAt?: number }) {
  const view = mount(RunMemoryLine, {
    props: { now: NOW, ...props },
    global: { plugins: [memoryRouter()] },
  })
  return { view, text: view.text().replace(/\s+/g, ' ').trim() }
}

test('ticket_run_shows_memory_received', () => {
  const { view, text } = shown({
    memory: { digest: 'd', received: ['2026-10-01-a', '2026-10-02-b'], left_out: ['2026-10-03-c'] },
  })

  expect(text).toBe('Memory: 2 entries 2026-10-01-a, 2026-10-02-b · 1 left out for the budget')
  expect(view.findAll('a').map((a) => a.attributes('href'))).toEqual([
    '/memory#2026-10-01-a',
    '/memory#2026-10-02-b',
  ])
})

test('a_run_given_no_memory_says_so', () => {
  expect(shown({ memory: null }).text).toBe('No memory')
})

test('ticket_run_shows_context_version', () => {
  const { text } = shown({ memory: null, contextAt: NOW - 60 })

  expect(text).toMatch(/^No memory · Context of \d+ \w+ \d\d:\d\d$/)
})
