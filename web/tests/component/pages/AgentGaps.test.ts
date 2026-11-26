// CF-918: each agent card and the agent form name the guarantees the chosen harness lacks.

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, expect, test, vi } from 'vitest'
import type { AgentDefinition } from '@/generated/AgentDefinition'
import { answer, memoryRouter, provideBoard, stubFetch } from '../../support/board'
import { present } from '../../support/present'
import AgentsPage from '@/pages/AgentsPage.vue'

const PERMISSIONS = 'permission requests reach the Inbox'
const STOP = 'the stop gate runs before it finishes'
const MEMORY = 'the memory store reaches it'

const GAPS = {
  claude: [],
  codex: [
    { guarantee: PERMISSIONS, why: 'its hook never runs' },
    { guarantee: STOP, why: 'its Stop hook runs inside srt' },
  ],
  omp: [
    { guarantee: PERMISSIONS, why: 'omp was not measured' },
    { guarantee: STOP, why: 'omp has no stop hook' },
    { guarantee: MEMORY, why: 'its context file is not known' },
  ],
}

const defined = (name: string, runtime: string): AgentDefinition => ({
  name,
  runtime,
  connection: '',
  model: '',
  roles: ['build'],
  max_tokens: null,
  max_seconds: null,
})

function served(url: string): Response {
  if (url === '/api/connections') return answer({ connections: [], kinds: [], problem: '' })
  if (url === '/api/connection-status') return answer({ connections: [], local: [], reach: {} })
  if (url === '/api/claude-agents') return answer({ agents: [], unread: [] })
  return answer({
    agents: [defined('builder', 'codex'), defined('writer', 'claude')],
    runtimes: ['claude', 'omp', 'codex'],
    roles: ['spec', 'build', 'review'],
    gaps: GAPS,
    doing: {},
    last: {},
    checks: {},
    starting: true,
    problem: '',
  })
}

let page: VueWrapper | null = null

async function shown(): Promise<VueWrapper> {
  stubFetch(served)
  const router = memoryRouter([
    { path: '/agents', component: AgentsPage },
    { path: '/:rest(.*)*', component: { render: () => null } },
  ])
  await router.push('/agents')
  page = mount(AgentsPage, {
    attachTo: document.body,
    global: { plugins: [router], provide: provideBoard(), stubs: { teleport: true } },
  })
  await flushPromises()
  return page
}

function button(scope: { findAll: VueWrapper['findAll'] }, name: string) {
  return present(
    scope.findAll('button').find((b) => b.text().trim() === name),
    `the ${name} button`,
  )
}

const listed = (scope: { findAll: VueWrapper['findAll'] }) =>
  scope.findAll('li').map((item) => item.text())

afterEach(() => {
  page?.unmount()
  page = null
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

// CF-918-R2
test('an_agent_card_names_its_runtime_s_gaps', async () => {
  const wrapper = await shown()

  const builder = wrapper.get('[role="listitem"][aria-label="builder"]')
  const line = builder.findAll('p').find((p) => p.text().startsWith('Lacks:'))
  const named = line?.findAll('span')

  expect(line?.text()).toBe(`Lacks: ${PERMISSIONS}, ${STOP}`)
  expect(named?.map((span) => span.attributes('title'))).toStrictEqual([
    'its hook never runs',
    'its Stop hook runs inside srt',
  ])
  expect(named?.map((span) => span.attributes('tabindex'))).toStrictEqual(['0', '0'])
  expect(wrapper.get('[role="listitem"][aria-label="writer"]').text()).not.toContain('Lacks:')
})

// CF-918-R3
test('the_agent_form_names_the_gaps_of_the_picked_harness', async () => {
  const wrapper = await shown()

  await button(wrapper, 'New agent').trigger('click')
  const form = wrapper.get('form[aria-label="New agent"]')
  const harness = form.findAll('select')[0]

  expect(form.text()).not.toContain('This harness lacks:')

  await present(harness, 'the Harness field').setValue('omp')

  expect(form.text()).toContain('This harness lacks:')
  expect(listed(form)).toStrictEqual([
    `${PERMISSIONS}: omp was not measured`,
    `${STOP}: omp has no stop hook`,
    `${MEMORY}: its context file is not known`,
  ])

  await present(harness, 'the Harness field').setValue('claude')

  expect(form.text()).not.toContain('This harness lacks:')
  expect(listed(form)).toStrictEqual([])
})

// CF-918-R3
test('the_edit_form_starts_with_the_gaps_of_the_agent_s_harness', async () => {
  const wrapper = await shown()
  const builder = wrapper.get('[role="listitem"][aria-label="builder"]')

  await button(builder, 'Edit builder').trigger('click')
  const form = wrapper.get('form[aria-label="Edit builder"]')

  expect(listed(form)).toStrictEqual([
    `${PERMISSIONS}: its hook never runs`,
    `${STOP}: its Stop hook runs inside srt`,
  ])
})
