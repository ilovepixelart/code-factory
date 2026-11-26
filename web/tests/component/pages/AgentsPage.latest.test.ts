// The Agents page reads the connections, the Claude Code agents and the scorers again after every
// change; only the latest read applies its answer, however late an earlier one arrives.

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, expect, test, vi } from 'vitest'
import type { ListedConnection } from '@/lib/connections'
import type { AgentList } from '@/lib/roster'
import { undone } from '@/lib/notice'
import { answer, memoryRouter, provideBoard, stubFetch } from '../../support/board'
import AgentsPage from '@/pages/AgentsPage.vue'

let page: VueWrapper | null = null

const roster: AgentList = {
  agents: [],
  runtimes: ['claude'],
  gaps: {},
  roles: ['build'],
  doing: {},
  last: {},
  checks: {},
  starting: true,
  problem: '',
}

const connectionNamed = (name: string): ListedConnection => ({
  name,
  kind: 'lm-studio',
  base_url: 'http://localhost:1234',
  key_env: '',
  key_set: false,
  here: true,
})

const scorerNamed = (name: string) => ({
  repository: 'sample',
  name,
  question: 'Did the session run the tests?',
  stage: '',
  sample: 1,
  threshold: 10,
  week: { yes: 1, no: 0, unclear: 0, pass_rate: 1 },
  month: { yes: 1, no: 0, unclear: 0, pass_rate: 1 },
  ticket: '',
})

const claudeNamed = (name: string) => ({
  name,
  description: '',
  model: '',
  tools: [],
  place: 'global',
  path: `/global/${name}.md`,
})

/** Mounts the page with the first read of `held` left unanswered and every later read of it, and
 *  every other read, answered at once; `late` answers the first read after the second applied. */
async function readTwice(
  address: string,
  held: string,
  answers: { first: unknown; second: unknown },
): Promise<{ wrapper: VueWrapper; late: () => Promise<void> }> {
  let release: (response: Response) => void = () => undefined
  let asked = 0
  stubFetch((url) => {
    if (url === held) {
      asked += 1
      return asked === 1
        ? new Promise<Response>((resolve) => (release = resolve))
        : answer(answers.second)
    }
    if (url === '/api/connections') return answer({ connections: [], kinds: [], problem: '' })
    if (url === '/api/connection-status') return answer({ connections: [], local: [], reach: {} })
    if (url === '/api/claude-agents') return answer({ agents: [], unread: [] })
    if (url === '/api/scorers') return answer({ scorers: [] })
    return answer(roster)
  })
  const router = memoryRouter([
    { path: '/agents', component: AgentsPage },
    { path: '/:rest(.*)*', component: { render: () => null } },
  ])
  await router.push(address)
  page = mount(AgentsPage, {
    attachTo: document.body,
    global: { plugins: [router], provide: provideBoard(), stubs: { teleport: true } },
  })
  await flushPromises()
  undone.value += 1
  await flushPromises()
  return {
    wrapper: page,
    late: async () => {
      release(answer(answers.first))
      await flushPromises()
    },
  }
}

afterEach(() => {
  page?.unmount()
  page = null
  vi.unstubAllGlobals()
})

test('an_older_connections_read_answering_last_never_replaces_the_newer_list', async () => {
  const { wrapper, late } = await readTwice('/agents?tab=connections', '/api/connections', {
    first: { connections: [connectionNamed('stale')], kinds: [], problem: '' },
    second: { connections: [connectionNamed('fresh')], kinds: [], problem: '' },
  })

  await late()

  const section = wrapper.get('section[aria-labelledby="connections-heading"]')
  expect(section.find('[role="listitem"][aria-label="fresh"]').exists()).toBe(true)
  expect(section.find('[role="listitem"][aria-label="stale"]').exists()).toBe(false)
})

test('an_older_claude_agents_read_answering_last_never_replaces_the_newer_list', async () => {
  const { wrapper, late } = await readTwice('/agents', '/api/claude-agents', {
    first: { agents: [claudeNamed('stale')], unread: [] },
    second: { agents: [claudeNamed('fresh')], unread: [] },
  })

  await late()

  const text = wrapper.get('section[aria-labelledby="claude-agents-heading"]').text()
  expect(text).toContain('fresh')
  expect(text).not.toContain('stale')
})

test('an_older_scorers_read_answering_last_never_replaces_the_newer_list', async () => {
  const { wrapper, late } = await readTwice('/agents', '/api/scorers', {
    first: { scorers: [scorerNamed('stale')] },
    second: { scorers: [scorerNamed('fresh')] },
  })

  await late()

  const text = wrapper.get('section[aria-labelledby="scorers-heading"]').text()
  expect(text).toContain('fresh')
  expect(text).not.toContain('stale')
})
