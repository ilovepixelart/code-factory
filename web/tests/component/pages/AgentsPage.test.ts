// CF-358: the Agents page lists the agents defined on this machine, says what none means, shows
// every refusal where it happened and disables a change's button while it is sent. CF-373: each
// agent is a card saying what it is doing, the cards needing attention first, and only changes
// are announced. CF-377: each card says what its agent last did. CF-401: each card of a local
// model says what its last model check found.

import { PRIMARY, variantOf } from '../../support/button'
import { DOMWrapper, flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, expect, test, vi } from 'vitest'
import type { AgentDefinition } from '@/generated/AgentDefinition'
import type { ConnectionStatus, Kind, ListedConnection } from '@/lib/connections'
import type { AgentList, Doing } from '@/lib/roster'
import { answer as confirmAnswer } from '@/lib/confirm'
import { undone } from '@/lib/notice'
import { PAGES } from '@/router'
import { answer, memoryRouter, provideBoard, stubFetch } from '../../support/board'
import { present } from '../../support/present'
import { INLINE, menuItem, openMenu } from '../../support/overlay'
import AgentsPage from '@/pages/AgentsPage.vue'
import { enter, labelled, validated } from '../../support/form'
import { BotIcon } from '@hugeicons/core-free-icons'

const ROLES = ['spec', 'build', 'review'] as const

const writer: AgentDefinition = {
  name: 'writer',
  runtime: 'claude',
  connection: '',
  model: 'claude-sonnet-4-5',
  roles: ['spec', 'spec'],
  max_tokens: 200_000,
  max_seconds: 3600,
}
const coder: AgentDefinition = {
  name: 'coder',
  runtime: 'opencode',
  connection: '',
  model: '',
  roles: ['build'],
  max_tokens: null,
  max_seconds: null,
}

function list(
  agents: AgentDefinition[],
  doing: AgentList['doing'] = {},
  starting = true,
  last: AgentList['last'] = {},
): AgentList {
  return {
    agents,
    runtimes: ['claude', 'opencode'],
    gaps: {},
    roles: [...ROLES],
    doing,
    last,
    checks: {},
    starting,
    problem: '',
  }
}

const KINDS: Kind[] = [
  { kind: 'anthropic', label: 'Anthropic', base_url: 'https://api.anthropic.com', key: 'required' },
  {
    kind: 'openrouter',
    label: 'OpenRouter',
    base_url: 'https://openrouter.ai/api',
    key: 'required',
  },
  { kind: 'lm-studio', label: 'LM Studio', base_url: 'http://localhost:1234', key: 'none' },
  { kind: 'ollama', label: 'Ollama', base_url: 'http://localhost:11434', key: 'none' },
  { kind: 'llama-cpp', label: 'llama.cpp', base_url: 'http://localhost:8080', key: 'none' },
  { kind: 'custom', label: 'Custom', base_url: '', key: 'none' },
]

const local: ListedConnection = {
  name: 'local',
  kind: 'lm-studio',
  base_url: 'http://localhost:1234',
  key_env: '',
  key_set: false,
  here: true,
}
const cloud: ListedConnection = {
  name: 'cloud',
  kind: 'openrouter',
  base_url: 'https://openrouter.ai/api',
  key_env: 'OPENROUTER_API_KEY',
  key_set: false,
  here: false,
}
const checked: ConnectionStatus = {
  connections: [
    {
      name: 'local',
      answers: true,
      models: [
        { id: 'qwen3-coder', context: 32_768, loaded: null },
        { id: 'gpt-oss-20b', context: null, loaded: null },
      ],
      problem: '',
    },
    { name: 'cloud', answers: false, models: [], problem: 'OPENROUTER_API_KEY is not set' },
  ],
  local: [],
  reach: { writer: 'answers' },
}
const NOTHING: ConnectionStatus = { connections: [], local: [], reach: {} }

/** The page's three reads: the agents, the connections and their status. */
function served(
  url: string,
  agents: AgentDefinition[],
  connections: ListedConnection[] = [],
  status: ConnectionStatus = NOTHING,
): Response {
  if (url === '/api/connections') return answer({ connections, kinds: KINDS, problem: '' })
  if (url === '/api/connection-status') return answer(status)
  if (url === '/api/claude-agents') return answer({ agents: [], unread: [] })
  return answer(list(agents))
}

/** The Connections tab. */
const CONNECTIONS = '/agents?tab=connections'

let page: VueWrapper | null = null

let router: ReturnType<typeof memoryRouter>

async function shown(address = '/agents'): Promise<VueWrapper> {
  router = memoryRouter([
    { path: '/agents', component: AgentsPage },
    { path: '/:rest(.*)*', component: { render: () => null } },
  ])
  await router.push(address)
  page = mount(AgentsPage, {
    attachTo: document.body,
    global: { plugins: [router], provide: provideBoard(), stubs: INLINE },
  })
  await flushPromises()
  return page
}

const agent = (wrapper: VueWrapper, name: string) =>
  wrapper.get(`[role="listitem"][aria-label="${name}"]`)

function button(scope: { findAll: VueWrapper['findAll'] }, name: string) {
  return present(
    scope.findAll('button').find((b) => b.text().trim() === name),
    `the ${name} button`,
  )
}

/** An item of an agent card's menu (Check, Test model, Remove), its menu opened first. */
async function action(scope: ReturnType<typeof agent>, name: string) {
  const trigger = scope.get('[data-menu]')
  if (trigger.attributes('aria-expanded') !== 'true') {
    await trigger.trigger('click')
    await flushPromises()
  }
  return present(
    scope.findAll('[role="menuitem"]').find((item) => item.text().trim() === name),
    `the ${name} item`,
  )
}

afterEach(() => {
  page?.unmount()
  page = null
  vi.unstubAllGlobals()
  vi.useRealTimers()
  document.body.innerHTML = ''
})

/** An empty state's title and the sentence under it. */
const emptyParts = (scope: Pick<VueWrapper, 'get'>) => [
  scope.get('[data-slot="empty-title"]').text(),
  scope.get('[data-slot="empty-description"]').text(),
]

test('the_agents_page_lists_each_agent', async () => {
  stubFetch((url) => served(url, [writer, coder]))

  const wrapper = await shown()

  const first = agent(wrapper, 'writer').text()
  const second = agent(wrapper, 'coder').text()
  for (const shownText of ['claude', 'claude-sonnet-4-5', 'Spec', 'Spec', 'no connection']) {
    expect(first).toContain(shownText)
  }
  expect(first).toContain('200,000 tokens')
  expect(first).toContain('60 min')
  for (const shownText of [
    'opencode',
    'harness default',
    'Build',
    'no connection',
    'no token or time limit',
  ]) {
    expect(second).toContain(shownText)
  }
  expect(first).not.toContain('no token or time limit')
  expect(PAGES.find((p) => p.path === '/agents')).toStrictEqual({
    path: '/agents',
    name: 'Agents',
    icon: BotIcon,
  })
})

test('the_agents_page_says_what_no_agents_means', async () => {
  stubFetch((url) => served(url, []))

  const wrapper = await shown()

  expect(emptyParts(wrapper)).toStrictEqual([
    'No agents defined',
    "Every run uses the default agent, each repository's harness and model.",
  ])
  expect(wrapper.findAll('[role="listitem"][aria-label]')).toHaveLength(0)
})

test('a_refused_agent_change_shows_its_reason', async () => {
  stubFetch((url, init) => {
    if (init?.method === 'POST') return answer({ detail: 'an agent named writer is defined' }, 409)
    if (init?.method === 'DELETE') return answer({ detail: 'no such agent' }, 404)
    return served(url, [writer])
  })
  const wrapper = await shown()

  await button(wrapper, 'New agent').trigger('click')
  const form = wrapper.get('form[aria-label="New agent"]')
  await form.get('input[name="name"]').setValue('writer')
  await form.trigger('submit')
  await validated()
  await (await action(agent(wrapper, 'writer'), 'Remove writer')).trigger('click')
  confirmAnswer(true)
  await flushPromises()

  const typed = wrapper.get('form[aria-label="New agent"] input[name="name"]')
  expect(wrapper.get('form[aria-label="New agent"]').text()).toContain(
    'an agent named writer is defined',
  )
  expect((typed.element as HTMLInputElement).value).toBe('writer')
  expect(agent(wrapper, 'writer').text()).toContain('no such agent')
})

test('agent_changes_disable_their_button_while_sent', async () => {
  const pending: ((response: Response) => void)[] = []
  const sent = stubFetch((url, init) =>
    init?.method === 'POST' || init?.method === 'DELETE'
      ? new Promise<Response>((done) => pending.push(done))
      : served(url, [writer]),
  )
  const wrapper = await shown()

  await button(wrapper, 'New agent').trigger('click')
  const form = wrapper.get('form[aria-label="New agent"]')
  await form.get('input[name="name"]').setValue('coder')
  await form.trigger('submit')
  await validated()
  const adding = button(form, 'Add').attributes('disabled')
  await (await action(agent(wrapper, 'writer'), 'Remove writer')).trigger('click')
  confirmAnswer(true)
  await flushPromises()
  const removing = (await action(agent(wrapper, 'writer'), 'Remove writer')).attributes(
    'data-disabled',
  )
  for (const done of pending) done(answer({ notice: 'Done', undo: null }))
  await flushPromises()

  expect(sent.filter((s) => s.method !== 'GET').map((s) => [s.method, s.url])).toStrictEqual([
    ['POST', '/api/agent-definitions'],
    ['DELETE', '/api/agent-definitions/writer'],
  ])
  expect(adding).toBeDefined()
  expect(removing).toBeDefined()
})

test('an_agent_is_changed_in_place_with_its_run_time_in_minutes', async () => {
  const sent = stubFetch((url, init) =>
    init?.method === 'PATCH'
      ? answer({ notice: 'Saved writer', undo: 'u-1' })
      : served(url, [writer]),
  )
  const wrapper = await shown()
  await button(wrapper, 'New agent').trigger('click')
  await button(wrapper.get('form[aria-label="New agent"]'), 'Cancel').trigger('click')

  await button(agent(wrapper, 'writer'), 'Edit writer').trigger('click')
  const form = wrapper.get('form[aria-label="Edit writer"]')
  await enter(labelled(form, 'Harness'), 'opencode')
  await enter(labelled(form, 'Model'), 'm-2')
  await enter(labelled(form, 'Build'), true)
  await enter(labelled(form, 'Token limit'), '5000')
  await enter(labelled(form, 'Run time limit (minutes)'), '30')
  await form.trigger('submit')
  await validated()

  expect(wrapper.find('form[aria-label="New agent"]').exists()).toBe(false)
  expect(sent.filter((s) => s.method === 'PATCH')).toStrictEqual([
    {
      method: 'PATCH',
      url: '/api/agent-definitions/writer',
      body: {
        name: 'writer',
        runtime: 'opencode',
        connection: '',
        model: 'm-2',
        roles: ['spec', 'spec', 'build'],
        types: [],
        labels: [],
        max_tokens: 5000,
        max_seconds: 1800,
        context: '',
      },
    },
  ])
  expect(wrapper.find('form[aria-label="Edit writer"]').exists()).toBe(false)
})

const connection = (wrapper: VueWrapper, name: string) =>
  wrapper
    .get('section[aria-labelledby="connections-heading"]')
    .get(`[role="listitem"][aria-label="${name}"]`)

// CF-529: the mark follows the context a run of the model would get (CF-389).
test('a_model_loaded_with_too_little_context_is_marked', async () => {
  const held: ConnectionStatus = {
    connections: [
      {
        name: 'local',
        answers: true,
        models: [
          { id: 'big', context: 131_072, loaded: 8192 },
          { id: 'tiny', context: null, loaded: 4096 },
          { id: 'short', context: 32_768, loaded: null },
          { id: 'roomy', context: 131_072, loaded: 65_536 },
        ],
        problem: '',
      },
    ],
    local: [],
    reach: {},
  }
  stubFetch((url) => served(url, [], [local], held))

  const wrapper = await shown(CONNECTIONS)
  const marked = connection(wrapper, 'local')
    .findAll('[data-model]')
    .filter((model) => model.find('[data-slot="badge"]').exists())
    .map((model) => model.get('code').text())

  expect(marked).toStrictEqual(['big', 'tiny', 'short'])
})

test('the_agents_page_lists_each_connection_and_its_status', async () => {
  const sent = stubFetch((url) => served(url, [], [local, cloud], checked))

  const wrapper = await shown(CONNECTIONS)
  const first = connection(wrapper, 'local').text()
  const second = connection(wrapper, 'cloud').text()
  await button(wrapper.get('section[aria-labelledby="connections-heading"]'), 'Check').trigger(
    'click',
  )
  await flushPromises()

  for (const shownText of [
    'LM Studio',
    'http://localhost:1234',
    'no key',
    'answers',
    'qwen3-coder',
    '32,768 tokens',
    'Under 64,000',
    'gpt-oss-20b',
  ]) {
    expect(first).toContain(shownText)
  }
  for (const shownText of [
    'OpenRouter',
    'https://openrouter.ai/api',
    'OPENROUTER_API_KEY not set',
  ]) {
    expect(second).toContain(shownText)
  }
  expect(second).not.toContain('answers')
  expect(second).not.toContain('is not set')
  expect(sent.filter((s) => s.url === '/api/connection-status')).toHaveLength(2)
})

test('the_agents_page_says_what_no_connections_mean', async () => {
  stubFetch((url) => served(url, []))

  const wrapper = await shown(CONNECTIONS)

  expect(emptyParts(wrapper.get('section[aria-labelledby="connections-heading"]'))).toStrictEqual([
    'No connections defined',
    "Agents run on their harness's own login.",
  ])
})

// CF-513: the owner calls the program an agent runs on its harness; the stored names stay runtime.
test('the_agent_form_labels_the_harness', async () => {
  stubFetch((url) => served(url, [writer]))
  const wrapper = await shown()

  await button(agent(wrapper, 'writer'), 'Edit writer').trigger('click')
  const form = wrapper.get('form[aria-label="Edit writer"]')
  const harness = labelled(form, 'Harness')

  expect(harness.findAll('option').map((o) => o.text())).toStrictEqual(['claude', 'opencode'])
  expect(form.text()).toContain("Empty: the harness's default model")
  expect(form.text()).toContain(
    "None: the harness's own login; a connection runs on the claude or opencode harness",
  )
  expect(form.text()).not.toMatch(/runtime/i)
})

test('the_agent_form_says_what_each_limit_holds', async () => {
  stubFetch((url) => served(url, [writer]))
  const wrapper = await shown()

  await button(agent(wrapper, 'writer'), 'Edit writer').trigger('click')
  const text = wrapper.get('form[aria-label="Edit writer"]').text()

  expect(text).toContain(
    "Tokens all of this agent's runs on one ticket may use together; empty: no limit",
  )
  expect(text).toContain(
    "Minutes all of this agent's runs on one ticket may take together; empty: no limit",
  )
})

test('the_agents_page_says_harness_not_runtime', async () => {
  const spare = { ...writer, name: 'spare', model: '' }
  stubFetch((url) => served(url, [spare]))
  const listed = await shown()
  const card = agent(listed, 'spare').text()
  const listedText = listed.text()
  listed.unmount()
  stubFetch((url) => served(url, []))
  const empty = await shown()

  expect(card).toContain('harness default')
  expect(card).toContain('claude harness · no connection')
  expect(listedText).toContain(
    "A column with no agent runs each repository's default harness and model.",
  )
  expect(emptyParts(empty)).toStrictEqual([
    'No agents defined',
    "Every run uses the default agent, each repository's harness and model.",
  ])
  expect(listedText).not.toMatch(/runtime/i)
  expect(empty.text()).not.toMatch(/runtime/i)
})

test('a_found_local_server_is_added_from_its_row', async () => {
  stubFetch((url) =>
    served(url, [], [], {
      connections: [],
      local: [
        {
          kind: 'lm-studio',
          base_url: 'http://localhost:1234',
          state: 'answers',
          models: [{ id: 'qwen3-coder', context: null, loaded: null }],
        },
      ],
      reach: {},
    }),
  )
  const wrapper = await shown(CONNECTIONS)

  const found = wrapper.get('section[aria-labelledby="found-heading"]')
  expect(found.text()).toContain('LM Studio')
  expect(found.text()).toContain('qwen3-coder')
  await button(found, 'Add LM Studio').trigger('click')

  const form = wrapper.get('form[aria-label="New connection"]')
  expect((form.get('select[name="kind"]').element as HTMLSelectElement).value).toBe('lm-studio')
  expect((form.get('input[name="base_url"]').element as HTMLInputElement).value).toBe(
    'http://localhost:1234',
  )
})

test('a_refused_connection_change_shows_its_reason', async () => {
  const pending: ((response: Response) => void)[] = []
  stubFetch((url, init) => {
    if (init?.method === 'POST')
      return answer({ detail: 'a connection named local is defined' }, 409)
    if (init?.method === 'DELETE') return new Promise<Response>((done) => pending.push(done))
    return served(url, [], [local])
  })
  const wrapper = await shown(CONNECTIONS)

  await button(wrapper, 'New connection').trigger('click')
  const form = wrapper.get('form[aria-label="New connection"]')
  await form.get('input[name="name"]').setValue('local')
  await form.trigger('submit')
  await validated()
  await button(connection(wrapper, 'local'), 'Remove local').trigger('click')
  confirmAnswer(true)
  await flushPromises()
  const removing = button(connection(wrapper, 'local'), 'Remove local').attributes('disabled')
  for (const done of pending) done(answer({ notice: 'Removed local', undo: null }))
  await flushPromises()

  const typed = wrapper.get('form[aria-label="New connection"] input[name="name"]')
  expect(wrapper.get('form[aria-label="New connection"]').text()).toContain(
    'a connection named local is defined',
  )
  expect((typed.element as HTMLInputElement).value).toBe('local')
  expect(removing).toBeDefined()
})

test('the_agent_form_offers_each_connection_and_its_models', async () => {
  const sent = stubFetch((url, init) =>
    init?.method === 'POST'
      ? answer({ notice: 'Added writer', undo: 'u-1' })
      : served(url, [], [local, cloud], checked),
  )
  const wrapper = await shown()

  await button(wrapper, 'New agent').trigger('click')
  const form = wrapper.get('form[aria-label="New agent"]')
  const choice = form.get('select[name="connection"]')
  const offered = choice.findAll('option').map((o) => o.text())
  await choice.setValue('local')
  await openMenu(wrapper, 'button[aria-label="Models of local"]')
  const suggested = wrapper.findAll('[role="menuitemradio"]').map((o) => o.text())
  await menuItem(wrapper, 'gpt-oss-20b').trigger('click')
  await flushPromises()
  const picked = (form.get('input[name="model"]').element as HTMLInputElement).value
  await form.get('input[name="name"]').setValue('writer')
  await form.trigger('submit')
  await validated()

  expect(offered).toStrictEqual(['None', 'local', 'cloud'])
  expect(suggested).toStrictEqual(['qwen3-coder', 'gpt-oss-20b'])
  expect(picked).toBe('gpt-oss-20b')
  expect(sent.find((s) => s.method === 'POST')?.body).toMatchObject({
    name: 'writer',
    connection: 'local',
    model: 'gpt-oss-20b',
  })
})

const spare: AgentDefinition = {
  name: 'spare',
  runtime: 'claude',
  connection: '',
  model: '',
  roles: [],
  max_tokens: null,
  max_seconds: null,
}

const WORKING = { state: 'working', repository: 'sample', id: 'CF-12' } as const

/** Where each part first shows in `text`, -1 for a part it lacks. */
const places = (text: string, parts: string[]) => parts.map((part) => text.indexOf(part))

test('each_agent_is_a_card_with_the_same_rows', async () => {
  stubFetch((url) => served(url, [{ ...writer, connection: 'local' }, spare]))
  const wrapper = await shown()

  const section = wrapper.get('section[aria-labelledby="agents-heading"]')
  // The agents' own list: each agent's actions menu is a list of its own (CF-1078).
  const items = section.findAll('[data-slot="item-group"] > [role="listitem"]')
  const cards = items
  const headings = cards.map((card) => card.get('h3').text())
  const first = places(cards[0]?.text() ?? '', [
    'writer',
    'Idle',
    'claude-sonnet-4-5',
    'claude harness · local',
    'Spec',
    'Spec',
    '200,000 tokens · 60 min',
    'No runs yet',
    'Edit writer',
  ])
  const second = places(cards[1]?.text() ?? '', [
    'spare',
    'Idle',
    'harness default',
    'claude harness · no connection',
    'no columns',
    'no token or time limit',
    'No runs yet',
    'Edit spare',
  ])
  await cards[0]?.trigger('click')
  const filled = wrapper.findAll(PRIMARY).map((b) => b.text().trim())

  expect(section.findAll('[data-slot="item-group"]')).toHaveLength(1)
  expect(items).toHaveLength(2)
  expect(headings).toStrictEqual(['writer', 'spare'])
  expect(cards.map((card) => card.text().startsWith(card.get('h3').text()))).toStrictEqual([
    true,
    true,
  ])
  for (const order of [first, second]) {
    expect(order).not.toContain(-1)
    expect(order).toStrictEqual([...order].sort((a, b) => a - b))
  }
  expect(cards.flatMap((card) => card.findAll('a'))).toHaveLength(0)
  expect(wrapper.find('form').exists()).toBe(false)
  expect(filled).toStrictEqual(['New agent'])
})

test('a_card_says_what_its_agent_is_doing', async () => {
  const held = { ...spare, name: 'held' }
  const spent = { ...spare, name: 'spent' }
  stubFetch((url) =>
    url === '/api/agent-definitions'
      ? answer(
          list([writer, coder, held, spent], {
            writer: WORKING,
            held: { state: 'waiting', repository: 'sample', id: 'CF-3' },
            spent: { state: 'over limit', repository: 'sample', id: 'CF-4' },
          }),
        )
      : served(url, []),
  )
  const wrapper = await shown()

  const link = agent(wrapper, 'writer').get('a')
  const states = ['writer', 'coder', 'held', 'spent'].map((name) =>
    agent(wrapper, name).find('[data-slot="badge"]').exists(),
  )

  expect(agent(wrapper, 'writer').text()).toContain('Working CF-12')
  expect([link.text(), link.attributes('href')]).toStrictEqual(['CF-12', '/tickets/sample/CF-12'])
  expect(agent(wrapper, 'coder').text()).toContain('Idle')
  expect(agent(wrapper, 'held').text()).toContain('Waiting')
  expect(agent(wrapper, 'spent').text()).toContain('Over limit')
  for (const name of ['coder', 'held', 'spent']) {
    expect(agent(wrapper, name).findAll('a')).toHaveLength(0)
  }
  expect(states).toEqual([true, true, true, true])
})

test('cards_needing_attention_come_first', async () => {
  const named = (name: string) => ({ ...spare, name })
  stubFetch((url) =>
    url === '/api/agent-definitions'
      ? answer(
          list(['a', 'b', 'c', 'd', 'e'].map(named), {
            b: WORKING,
            c: { state: 'over limit', repository: 'sample', id: 'CF-4' },
            d: { state: 'waiting', repository: 'sample', id: 'CF-3' },
          }),
        )
      : served(url, []),
  )

  const wrapper = await shown()

  expect(
    wrapper.findAll('[role="listitem"][aria-label]').map((card) => card.attributes('aria-label')),
  ).toStrictEqual(['c', 'd', 'b', 'a', 'e'])
})

/** A control's text without what only screen readers get. */
function visible(element: Element): string {
  const copy = element.cloneNode(true) as Element
  for (const hidden of copy.querySelectorAll('.sr-only')) hidden.remove()
  return copy.textContent.trim()
}

test('card_actions_are_named_for_their_agent', async () => {
  stubFetch((url) => served(url, [writer, coder]))
  const wrapper = await shown()

  const edit = button(agent(wrapper, 'writer'), 'Edit writer')
  const remove = await action(agent(wrapper, 'writer'), 'Remove writer')
  const shownWords = [visible(edit.element), visible(remove.element)]
  await edit.trigger('click')
  const form = wrapper.get('form[aria-label="Edit writer"]')
  const item = present(form.element.closest('[role="listitem"]'), 'the edited item')

  expect(shownWords).toStrictEqual(['Edit', 'Remove'])
  expect(button(agent(wrapper, 'coder'), 'Edit coder').exists()).toBe(true)
  expect(item.getAttribute('aria-label')).toBe('writer')
})

test('the_page_announces_only_changes', async () => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] })
  let doing: AgentList['doing'] = {}
  const sent = stubFetch((url) =>
    url === '/api/agent-definitions' ? answer(list([writer], doing)) : served(url, []),
  )
  const wrapper = await shown()
  const region = wrapper.get('[role="status"]')
  const first = region.text()
  const edit = button(agent(wrapper, 'writer'), 'Edit writer')
  ;(edit.element as HTMLButtonElement).focus()

  doing = { writer: WORKING }
  await vi.advanceTimersByTimeAsync(3000)
  await flushPromises()
  const said = region.text()
  let changes = 0
  new MutationObserver((records) => (changes += records.length)).observe(region.element, {
    subtree: true,
    childList: true,
    characterData: true,
  })
  await vi.advanceTimersByTimeAsync(3000)
  await flushPromises()

  expect(region.attributes('aria-live')).toBe('polite')
  expect(first).toBe('')
  expect(said).toBe('writer started CF-12')
  expect(changes).toBe(0)
  expect(region.text()).toBe('writer started CF-12')
  expect(sent.filter((s) => s.url === '/api/agent-definitions')).toHaveLength(3)
  expect(document.activeElement).toBe(edit.element)
})

const BY_HAND =
  'Agents start only by hand: no repository sets [agents] slots in .code-factory/config.toml.'

test('the_page_says_when_agents_start_only_by_hand', async () => {
  stubFetch((url) =>
    url === '/api/agent-definitions' ? answer(list([writer], {}, false)) : served(url, []),
  )
  const byHand = await shown()
  const saidByHand = byHand.text()
  byHand.unmount()
  stubFetch((url) =>
    url === '/api/agent-definitions' ? answer(list([writer], {}, true)) : served(url, []),
  )
  const queued = await shown()

  expect(saidByHand).toContain(BY_HAND)
  expect(queued.text()).not.toContain(BY_HAND)
})

test('a_paused_card_says_so_and_offers_resume', async () => {
  // 14:02 in this browser's zone, whatever it is, on the day the page reads it (CF-480-R5).
  const at = new Date(2026, 8, 21, 14, 2).getTime() / 1000
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date(2026, 8, 21, 18, 0))
  const resting = { ...spare, name: 'resting', paused_at: at }
  const finishing = { ...writer, paused_at: at }
  stubFetch((url) =>
    url === '/api/agent-definitions'
      ? answer(list([coder, resting, finishing], { writer: WORKING }))
      : served(url, []),
  )
  const wrapper = await shown()

  expect(agent(wrapper, 'resting').text()).toContain('Paused 14:02')
  expect(agent(wrapper, 'writer').text()).toContain('Finishing CF-12, then paused')
  expect(button(agent(wrapper, 'resting'), 'Resume resting').exists()).toBe(true)
  expect(button(agent(wrapper, 'coder'), 'Pause coder').exists()).toBe(true)
  expect(
    wrapper.findAll('[role="listitem"][aria-label]').map((card) => card.attributes('aria-label')),
  ).toStrictEqual(['writer', 'resting', 'coder'])
})

test('the_page_shows_claude_code_agents_read_only', async () => {
  stubFetch((url) =>
    url === '/api/claude-agents'
      ? answer({
          agents: [
            {
              name: 'code-reviewer',
              description: 'Reviews a diff.',
              model: '',
              tools: ['Read', 'Grep'],
              place: 'global',
              path: '/home/me/.claude/agents/code-reviewer.md',
            },
            {
              name: 'ticket-worker',
              description: 'Takes one ticket to a pull request.',
              model: 'sonnet',
              tools: [],
              place: 'sample',
              path: '/r/sample/.claude/agents/ticket-worker.md',
            },
          ],
          unread: [{ path: '/r/sample/.claude/agents/notes.md', why: 'no front matter' }],
        })
      : served(url, []),
  )
  const wrapper = await shown()
  const section = wrapper.get('section[aria-labelledby="claude-agents-heading"]')
  const rows = section.findAll('[data-slot="item"]')
  expect(section.findAll('[data-slot="card"]')).toHaveLength(3)
  const empty = await (async () => {
    wrapper.unmount()
    stubFetch((url) => served(url, []))
    return (await shown()).get('section[aria-labelledby="claude-agents-heading"]').text()
  })()

  expect(section.get('h2').text()).toBe('Claude Code agents, 2')
  expect(rows.map((row) => row.text())).toStrictEqual([
    'code-reviewerglobalReviews a diff.inherits model · Read, Grep',
    'ticket-workersampleTakes one ticket to a pull request.sonnet · all tools',
    'not read: /r/sample/.claude/agents/notes.md no front matter',
  ])
  expect(section.findAll('button')).toHaveLength(0)
  expect(empty).toContain('No Claude Code agents')
  expect(empty).toContain("They are defined in ~/.claude/agents and this project's .claude/agents.")
})

// CF-378: each card says whether its connection answers, from the page's one check.
const down: ListedConnection = { ...local, name: 'down', base_url: 'http://localhost:1235' }
const withDown: ConnectionStatus = {
  connections: [
    ...checked.connections,
    { name: 'down', answers: false, models: [], problem: 'no answer' },
  ],
  local: [],
  // As the server words each agent's model from this check (connections::reach).
  reach: {
    listed: 'answers',
    unlisted: 'model not listed',
    unset: 'answers',
    keyless: 'does not answer',
    unreached: 'does not answer',
    c: 'does not answer',
    e: 'does not answer',
    writer: 'does not answer',
  },
}
const REACH = ['Answers', 'Does not answer', 'Key missing', 'Model not listed', 'Checking']

/** The connection words a card shows. */
const reach = (wrapper: VueWrapper, name: string) =>
  REACH.filter((word) => agent(wrapper, name).text().includes(word))

test('a_card_says_whether_its_connection_answers', async () => {
  const on = (name: string, connection: string, model: string) => ({
    ...spare,
    name,
    connection,
    model,
  })
  stubFetch((url) =>
    served(
      url,
      [
        on('listed', 'local', 'qwen3-coder'),
        on('unlisted', 'local', 'gpt-5'),
        on('unset', 'local', ''),
        on('keyless', 'cloud', 'qwen3-coder'),
        on('unreached', 'down', 'qwen3-coder'),
        on('alone', '', ''),
      ],
      [local, cloud, down],
      withDown,
    ),
  )

  const wrapper = await shown()

  expect(reach(wrapper, 'listed')).toStrictEqual(['Answers'])
  expect(reach(wrapper, 'unlisted')).toStrictEqual(['Model not listed'])
  expect(reach(wrapper, 'unset')).toStrictEqual(['Answers'])
  expect(reach(wrapper, 'keyless')).toStrictEqual(['Key missing'])
  expect(reach(wrapper, 'unreached')).toStrictEqual(['Does not answer'])
  expect(reach(wrapper, 'alone')).toStrictEqual([])
  expect(agent(wrapper, 'listed').text()).toContain('claude harness · local Answers')
})

test('a_card_checks_its_connection', async () => {
  const pending: ((response: Response) => void)[] = []
  let asked = 0
  stubFetch((url) => {
    if (url !== '/api/connection-status')
      return served(url, [{ ...writer, model: 'qwen3-coder', connection: 'local' }, coder], [local])
    asked += 1
    return asked === 1 ? answer(checked) : new Promise<Response>((done) => pending.push(done))
  })
  const wrapper = await shown()
  const before = reach(wrapper, 'writer')

  await (await action(agent(wrapper, 'writer'), 'Check writer')).trigger('click')
  await flushPromises()
  const during = reach(wrapper, 'writer')
  const disabled = (await action(agent(wrapper, 'writer'), 'Check writer')).attributes(
    'data-disabled',
  )
  for (const done of pending) done(answer(checked))
  await flushPromises()

  expect(before).toStrictEqual(['Answers'])
  expect(asked).toBe(2)
  expect(during).toStrictEqual(['Checking'])
  expect(disabled).toBeDefined()
  expect(reach(wrapper, 'writer')).toStrictEqual(['Answers'])
  expect(
    (await action(agent(wrapper, 'writer'), 'Check writer')).attributes('data-disabled'),
  ).toBeUndefined()
  const other = agent(wrapper, 'coder')
  expect(other.findAll('button:not([data-menu])').map((b) => visible(b.element))).toStrictEqual([
    'Pause',
    'Edit',
  ])
  await action(other, 'Remove coder')
  expect(other.findAll('[role="menuitem"]').map((i) => visible(i.element))).toStrictEqual([
    'Remove',
  ])
})

test('cards_whose_connection_fails_need_attention', async () => {
  const named = (name: string) => ({ ...spare, name })
  const pending: ((response: Response) => void)[] = []
  let asked = 0
  stubFetch((url) => {
    if (url === '/api/agent-definitions')
      return answer(
        list(
          [
            named('a'),
            named('b'),
            { ...named('c'), connection: 'down' },
            named('d'),
            { ...named('e'), connection: 'down' },
          ],
          {
            b: WORKING,
            d: { state: 'waiting', repository: 'sample', id: 'CF-3' },
            e: { state: 'over limit', repository: 'sample', id: 'CF-4' },
          },
        ),
      )
    if (url !== '/api/connection-status') return served(url, [], [down])
    asked += 1
    return asked === 1 ? answer(withDown) : new Promise<Response>((done) => pending.push(done))
  })
  const order = (wrapper: VueWrapper) =>
    wrapper
      .get('section[aria-labelledby="agents-heading"]')
      .findAll('[role="listitem"][aria-label]')
      .map((card) => card.attributes('aria-label'))

  const wrapper = await shown()
  const opened = order(wrapper)
  await (await action(agent(wrapper, 'c'), 'Check c')).trigger('click')
  await flushPromises()
  const checking = order(wrapper)

  expect(opened).toStrictEqual(['e', 'd', 'c', 'b', 'a'])
  expect(reach(wrapper, 'c')).toStrictEqual(['Checking'])
  expect(checking).toStrictEqual(['e', 'd', 'c', 'b', 'a'])
})

// CF-474-3: a connection check the board refuses, or does not answer, says so and leaves Check
// usable, the cards keeping what the last finished check found.
test('a_failed_connection_check_says_why_and_leaves_check_usable', async () => {
  let asked = 0
  stubFetch((url) => {
    if (url !== '/api/connection-status')
      return served(url, [{ ...writer, model: 'qwen3-coder', connection: 'local' }], [local])
    asked += 1
    if (asked === 1) return answer(checked)
    if (asked === 2) return answer({ detail: 'the board took longer than 30 s to answer' }, 503)
    return Promise.reject(new TypeError('Failed to fetch'))
  })
  const wrapper = await shown()

  await (await action(agent(wrapper, 'writer'), 'Check writer')).trigger('click')
  await flushPromises()
  const refused = wrapper.text()
  const usable = (await action(agent(wrapper, 'writer'), 'Check writer')).attributes(
    'data-disabled',
  )
  const kept = reach(wrapper, 'writer')
  await (await action(agent(wrapper, 'writer'), 'Check writer')).trigger('click')
  await flushPromises()

  expect(refused).toContain('the board took longer than 30 s to answer')
  expect(usable).toBeUndefined()
  expect(kept).toStrictEqual(['Answers'])
  expect(wrapper.text()).toContain('The board did not answer; try again.')
  expect(
    (await action(agent(wrapper, 'writer'), 'Check writer')).attributes('data-disabled'),
  ).toBeUndefined()
  await router.push(CONNECTIONS)
  expect(
    button(wrapper.get('section[aria-labelledby="connections-heading"]'), 'Check').attributes(
      'disabled',
    ),
  ).toBeUndefined()
})

test('a_first_connection_check_that_fails_leaves_no_card_checking', async () => {
  stubFetch((url) =>
    url === '/api/connection-status'
      ? answer({ detail: 'connections.json does not read' }, 500)
      : served(url, [{ ...writer, model: 'qwen3-coder', connection: 'local' }], [local]),
  )

  const wrapper = await shown()

  expect(reach(wrapper, 'writer')).toStrictEqual([])
  expect(wrapper.text()).toContain('connections.json does not read')
  expect(
    (await action(agent(wrapper, 'writer'), 'Check writer')).attributes('data-disabled'),
  ).toBeUndefined()
  await router.push(CONNECTIONS)
  expect(wrapper.get('section[aria-labelledby="connections-heading"]').text()).not.toContain(
    'checking',
  )
})

test('an_older_connection_check_never_overwrites_a_newer_one', async () => {
  const pending: ((response: Response) => void)[] = []
  let asked = 0
  stubFetch((url) => {
    if (url !== '/api/connection-status')
      return served(url, [{ ...writer, model: 'qwen3-coder', connection: 'down' }], [down])
    asked += 1
    return asked === 1 ? new Promise<Response>((done) => pending.push(done)) : answer(withDown)
  })
  const wrapper = await shown()

  undone.value += 1
  await flushPromises()
  for (const done of pending)
    done(
      answer({
        ...withDown,
        connections: [{ name: 'down', answers: true, models: [], problem: '' }],
        reach: { writer: 'answers' },
      }),
    )
  await flushPromises()

  expect(asked).toBe(2)
  expect(reach(wrapper, 'writer')).toStrictEqual(['Does not answer'])
})

// CF-474-3: a first read of the agents the board refuses says why instead of a blank page.
test('a_refused_first_read_of_the_agents_says_why', async () => {
  stubFetch((url) =>
    url === '/api/agent-definitions'
      ? answer({ detail: 'agents.json does not read' }, 409)
      : served(url, []),
  )

  const wrapper = await shown()

  expect(wrapper.text()).toContain('agents.json does not read')
})

const buttons = (wrapper: VueWrapper) => wrapper.findAll('button').map((b) => b.text().trim())

test('the_agents_page_says_it_is_reading_the_agents_and_offers_no_new_agent', async () => {
  stubFetch((url) =>
    url === '/api/agent-definitions' ? new Promise<Response>(() => undefined) : served(url, []),
  )

  const wrapper = await shown()

  expect(wrapper.text()).toContain('Reading the agents')
  expect(buttons(wrapper)).not.toContain('New agent')
})

test('a_refused_first_read_of_the_agents_is_read_again_from_the_page', async () => {
  let refuse = true
  stubFetch((url) =>
    url === '/api/agent-definitions' && refuse
      ? answer({ detail: 'agents.json does not read' }, 500)
      : served(url, [writer]),
  )

  const wrapper = await shown()

  expect(wrapper.text()).toContain('agents.json does not read')
  expect(buttons(wrapper)).not.toContain('New agent')
  expect(wrapper.find('form[aria-label="New agent"]').exists()).toBe(false)

  refuse = false
  await button(wrapper, 'Read again').trigger('click')
  await flushPromises()

  expect(wrapper.find('[role="listitem"][aria-label="writer"]').exists()).toBe(true)
  expect(buttons(wrapper)).toContain('New agent')
  expect(wrapper.find('form[aria-label="New agent"]').exists()).toBe(false)
})

test('the_connections_tab_says_it_is_reading_the_connections', async () => {
  stubFetch((url) =>
    url === '/api/connections' ? new Promise<Response>(() => undefined) : served(url, []),
  )

  const wrapper = await shown(CONNECTIONS)

  expect(wrapper.text()).toContain('Reading the connections')
})

test('a_refused_read_of_the_connections_says_why_and_is_read_again', async () => {
  let refuse = true
  stubFetch((url) =>
    url === '/api/connections' && refuse
      ? answer({ detail: 'connections.json does not read' }, 500)
      : served(url, [], [local]),
  )

  const wrapper = await shown(CONNECTIONS)

  expect(wrapper.text()).toContain('connections.json does not read')

  refuse = false
  await button(wrapper, 'Read again').trigger('click')
  await flushPromises()

  expect(wrapper.find(`[role="listitem"][aria-label="${local.name}"]`).exists()).toBe(true)
})

// CF-389: a card says its model is loaded with less context than a run needs (64,000 tokens).
const loadedAt = (
  loaded: (number | null)[],
  reach: ConnectionStatus['reach'],
): ConnectionStatus => ({
  connections: [
    {
      name: 'local',
      answers: true,
      models: loaded.map((at, i) => ({ id: `m-${String(i)}`, context: 131_072, loaded: at })),
      problem: '',
    },
  ],
  local: [],
  reach,
})

/** A card's connection line, its whitespace runs as one space. */
const line = (wrapper: VueWrapper, name: string) =>
  agent(wrapper, name).findAll('p')[1]?.text().replace(/\s+/g, ' ')

test('a_card_says_its_model_is_loaded_with_too_little_context', async () => {
  const on = (name: string, model: string) => ({ ...spare, name, connection: 'local', model })
  stubFetch((url) =>
    served(
      url,
      [on('short', 'm-0'), on('below', 'm-1'), on('enough', 'm-2'), on('unloaded', 'm-3')],
      [local],
      loadedAt([8192, 63_999, 64_000, null], {
        short: 'context 8,192 of 64,000',
        below: 'context 63,999 of 64,000',
        enough: 'answers',
        unloaded: 'answers',
      }),
    ),
  )

  const wrapper = await shown()

  expect(line(wrapper, 'short')).toBe('claude harness · local Context 8,192 of 64,000')
  expect(line(wrapper, 'below')).toBe('claude harness · local Context 63,999 of 64,000')
  expect(line(wrapper, 'enough')).toBe('claude harness · local Answers')
  expect(line(wrapper, 'unloaded')).toBe('claude harness · local Answers')
  const badges = agent(wrapper, 'short')
    .findAll('[data-slot="badge"]')
    .map((b) => b.text())
  expect(badges).toContain('Context 8,192 of 64,000')
})

test('a_card_short_of_context_needs_attention', async () => {
  stubFetch((url) =>
    url === '/api/agent-definitions'
      ? answer(
          list(
            [
              { ...spare, name: 'a', connection: 'local', model: 'm-1' },
              { ...spare, name: 'b' },
              { ...spare, name: 'c', connection: 'local', model: 'm-0' },
            ],
            { b: WORKING },
          ),
        )
      : served(
          url,
          [],
          [local],
          loadedAt([8192, null], { a: 'answers', c: 'context 8,192 of 64,000' }),
        ),
  )

  const wrapper = await shown()

  expect(
    wrapper
      .get('section[aria-labelledby="agents-heading"]')
      .findAll('[role="listitem"][aria-label]')
      .map((card) => card.attributes('aria-label')),
  ).toStrictEqual(['c', 'b', 'a'])
})

/** A card's text with each run of whitespace as one space. */
const said = (wrapper: VueWrapper, name: string) => agent(wrapper, name).text().replace(/\s+/g, ' ')

test('a_card_says_what_its_agent_last_did', async () => {
  const now = 1_790_001_000
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(now * 1000)
  stubFetch((url) =>
    url === '/api/agent-definitions'
      ? answer(
          list([writer, coder], {}, true, {
            writer: {
              run: 'r1',
              repository: 'sample',
              id: 'CF-9',
              stage: 'build',
              at: now - 7500,
              outcome: 'finished',
            },
            coder: {
              run: 'r1',
              repository: 'sample',
              id: 'CF-12',
              stage: 'review',
              at: now - 184,
              outcome: 'running',
            },
          }),
        )
      : served(url, []),
  )
  const wrapper = await shown()

  const links = agent(wrapper, 'writer')
    .findAll('a')
    .map((link) => [link.text(), link.attributes('href')])

  expect(said(wrapper, 'writer')).toContain('Last: CF-9 Build, ended 2.1h ago, finished')
  expect(links).toStrictEqual([['CF-9', '/tickets/sample/CF-9']])
  expect(said(wrapper, 'coder')).toContain('Last: CF-12 Review, started 3m ago, running')
})

// CF-490: an age reads as Flow and the Inbox write it, in days past a day and seconds under a minute.
test('a_run_ended_days_ago_reads_in_days', async () => {
  const now = 1_790_001_000
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(now * 1000)
  stubFetch((url) =>
    url === '/api/agent-definitions'
      ? answer(
          list([writer, coder], {}, true, {
            writer: {
              run: 'r1',
              repository: 'sample',
              id: 'CF-9',
              stage: 'build',
              at: now - 358_740,
              outcome: 'finished',
            },
            coder: {
              run: 'r1',
              repository: 'sample',
              id: 'CF-12',
              stage: 'review',
              at: now - 12,
              outcome: 'running',
            },
          }),
        )
      : served(url, []),
  )
  const wrapper = await shown()

  expect(said(wrapper, 'writer')).toContain('Last: CF-9 Build, ended 4.2d ago, finished')
  expect(said(wrapper, 'coder')).toContain('Last: CF-12 Review, started 12s ago, running')
})

test('a_card_says_its_last_run_left_work_uncommitted', async () => {
  const now = 1_790_001_000
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(now * 1000)
  stubFetch((url) =>
    url === '/api/agent-definitions'
      ? answer(
          list([writer], {}, true, {
            writer: {
              run: 'r1',
              repository: 'sample',
              id: 'CF-9',
              stage: 'build',
              at: now - 7500,
              outcome: 'uncommitted',
            },
          }),
        )
      : served(url, []),
  )
  const wrapper = await shown()

  expect(said(wrapper, 'writer')).toContain('Last: CF-9 Build, ended 2.1h ago, uncommitted')
})

test('a_card_says_its_last_run_hit_a_usage_limit', async () => {
  const now = 1_790_001_000
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(now * 1000)
  const last = (until: number) => ({
    run: 'r1',
    repository: 'sample',
    id: 'CF-9',
    stage: 'build' as const,
    at: now - 300,
    outcome: 'usage limit' as const,
    until,
  })
  stubFetch((url) =>
    url === '/api/agent-definitions'
      ? answer(list([writer, coder], {}, true, { writer: last(now + 3600), coder: last(now - 5) }))
      : served(url, []),
  )
  const wrapper = await shown()

  expect(said(wrapper, 'writer')).toContain(
    'Last: CF-9 Build, ended 5m ago, usage limit, resumes in 1h',
  )
  expect(said(wrapper, 'coder')).toContain('Last: CF-9 Build, ended 5m ago, usage limit, resuming')
})

test('a_card_says_why_its_resume_was_refused', async () => {
  const now = 1_790_001_000
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(now * 1000)
  const last = {
    run: 'r1',
    repository: 'sample',
    id: 'CF-9',
    stage: 'build' as const,
    at: now - 300,
    outcome: 'usage limit' as const,
    until: now + 240,
    refused: 'agents are stopped',
  }
  stubFetch((url) =>
    url === '/api/agent-definitions'
      ? answer(list([writer], {}, true, { writer: last }))
      : served(url, []),
  )
  const wrapper = await shown()

  expect(said(wrapper, 'writer')).toContain(
    'Last: CF-9 Build, ended 5m ago, usage limit, resume refused: agents are stopped',
  )
  expect(said(wrapper, 'writer')).not.toContain('resumes in')
})

test('a_card_without_runs_says_so', async () => {
  stubFetch((url) => served(url, [writer]))
  const wrapper = await shown()

  expect(said(wrapper, 'writer')).toContain('No runs yet')
  expect(agent(wrapper, 'writer').findAll('a')).toHaveLength(0)
})

/** Working CF-12 with `tokens` reported (null for none yet) and `seconds` run. */
const using = (tokens: number | null, seconds: number): Doing => ({
  ...WORKING,
  usage: { tokens, seconds },
})

/** The Context button of the limit `name` (the agent and the limit) on the page. */
const meter = (wrapper: VueWrapper, name: string) => wrapper.get(`button[aria-label^="${name}, "]`)

/** The Context buttons of one agent's card. */
const metersOf = (wrapper: VueWrapper, name: string) =>
  agent(wrapper, name)
    .findAll('button')
    .filter((b) => /^\S+ (tokens|time), /.test(b.attributes('aria-label') ?? ''))

/** The tone a limit is drawn in, read from its button's variant. */
function toneOf(wrapper: VueWrapper, name: string): string {
  const TONES: Record<string, string> = {
    outline: 'default',
    default: 'warning',
    destructive: 'error',
  }
  return TONES[variantOf(meter(wrapper, name))] ?? 'mixed'
}

test('a_claim_shows_its_usage_against_each_limit', async () => {
  const big = { ...writer, name: 'big', max_tokens: 2_000_000 }
  const near = { ...writer, name: 'near', max_tokens: 2_000_000 }
  const few = { ...writer, name: 'few' }
  const free = { ...coder, name: 'free' }
  stubFetch((url) =>
    url === '/api/agent-definitions'
      ? answer(
          list([writer, big, near, few, free, spare], {
            writer: using(150_000, 720),
            big: using(1_234_567, 59),
            near: using(1_999_999, 3599),
            few: { ...using(999, 0), state: 'waiting' },
            free: using(5, 10),
          }),
        )
      : served(url, []),
  )
  const wrapper = await shown()

  const tokens = meter(wrapper, 'writer tokens')
  expect([tokens.text(), tokens.attributes('aria-label')]).toEqual([
    '75% tokens',
    'writer tokens, 150 k of 200 k tokens',
  ])
  await tokens.trigger('focus')
  await vi.waitFor(() => {
    expect(
      document.querySelector('[role="progressbar"][aria-label="writer tokens used"]'),
    ).not.toBeNull()
  })
  const bar = present(
    document.querySelector('[role="progressbar"][aria-label="writer tokens used"]'),
    'the bar',
  )
  expect(bar.getAttribute('aria-valuenow')).toBe('75')
  expect(bar.closest('[data-slot="hover-card-content"]')?.textContent).toContain(
    '150 k of 200 k tokens',
  )
  const label = (name: string) => meter(wrapper, name).attributes('aria-label')
  expect(label('writer time')).toBe('writer time, 12 of 60 min')
  expect(label('big tokens')).toBe('big tokens, 1.2 M of 2 M tokens')
  expect(label('big time')).toBe('big time, 0 of 60 min')
  expect(label('near tokens')).toBe('near tokens, 1.9 M of 2 M tokens')
  expect(label('near time')).toBe('near time, 59 of 60 min')
  expect(label('few tokens')).toBe('few tokens, 999 of 200 k tokens')
  expect(meter(wrapper, 'few tokens').text()).toBe('0% tokens')
  expect(metersOf(wrapper, 'free')).toHaveLength(0)
  expect(metersOf(wrapper, 'spare')).toHaveLength(0)
})

test('a_meter_warns_from_75_and_errs_at_100_percent', async () => {
  const counts = [749, 750, 999, 1000]
  const seconds = [2699, 2700, 3599, 3600]
  const named = counts.map((count) => ({
    ...writer,
    name: `at${String(count)}`,
    max_tokens: 1000,
  }))
  const doing = Object.fromEntries(
    named.map((a, i) => [a.name, using(counts[i] ?? 0, seconds[i] ?? 0)]),
  )
  stubFetch((url) =>
    url === '/api/agent-definitions' ? answer(list(named, doing)) : served(url, []),
  )
  const wrapper = await shown()

  expect(named.map((a) => toneOf(wrapper, `${a.name} tokens`))).toStrictEqual([
    'default',
    'warning',
    'warning',
    'error',
  ])
  expect(named.map((a) => toneOf(wrapper, `${a.name} time`))).toStrictEqual([
    'default',
    'warning',
    'warning',
    'error',
  ])
})

test('a_claim_without_reported_tokens_shows_time_alone', async () => {
  const timed = { ...writer, name: 'timed', max_tokens: null }
  stubFetch((url) =>
    url === '/api/agent-definitions'
      ? answer(list([writer, timed], { writer: using(null, 60), timed: using(null, 60) }))
      : served(url, []),
  )
  const wrapper = await shown()

  const meters = metersOf(wrapper, 'writer')
  expect(meters.map((m) => m.attributes('aria-label'))).toStrictEqual(['writer time, 1 of 60 min'])
  expect(agent(wrapper, 'writer').text()).toContain('claude reports tokens when its run ends')
  expect(agent(wrapper, 'timed').text()).not.toContain('reports tokens')
})

test('a_meter_crossing_a_threshold_is_announced', async () => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] })
  let doing: AgentList['doing'] = { writer: using(140_000, 60) }
  stubFetch((url) =>
    url === '/api/agent-definitions' ? answer(list([writer], doing)) : served(url, []),
  )
  const wrapper = await shown()
  const region = wrapper.get('[role="status"]')
  const next = async (now: Doing): Promise<string> => {
    doing = { writer: now }
    await vi.advanceTimersByTimeAsync(3000)
    await flushPromises()
    return region.text()
  }

  const first = region.text()
  const warned = await next(using(150_000, 60))
  let changes = 0
  new MutationObserver((records) => (changes += records.length)).observe(region.element, {
    subtree: true,
    childList: true,
    characterData: true,
  })
  await next(using(160_000, 120))
  const within = changes
  const limited = await next(using(160_000, 3600))
  const both = await next(using(200_000, 3600))
  await next(using(null, 0))
  const other = await next({ ...using(190_000, 60), id: 'CF-13' })

  expect(first).toBe('')
  expect(warned).toBe('writer at 75% of its tokens')
  expect(within).toBe(0)
  expect(limited).toBe('writer at its time limit')
  expect(both).toBe('writer at its token limit')
  expect(other).toBe('writer started CF-13')
})

test('a_card_says_what_its_model_check_found', async () => {
  const now = 1_790_001_000
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(now * 1000)
  const on = (name: string, connection: string, model = 'm-1') => ({
    ...spare,
    name,
    connection,
    model,
  })
  const result = (passed: boolean, problem: string) => ({
    runtime: 'claude',
    connection: 'local',
    model: 'm-1',
    passed,
    problem,
    at: now - 120,
  })
  const answering: ConnectionStatus = {
    connections: [
      {
        name: 'local',
        answers: true,
        models: [{ id: 'm-1', context: null, loaded: null }],
        problem: '',
      },
    ],
    local: [],
    reach: {},
  }
  const pending: ((response: Response) => void)[] = []
  const sent = stubFetch((url) => {
    if (url === '/api/agent-definitions')
      return answer({
        ...list([
          on('fresh', 'local'),
          on('good', 'local'),
          on('bad', 'local'),
          on('paid', 'cloud'),
          on('vague', 'local', ''),
        ]),
        checks: { good: result(true, ''), bad: result(false, 'answered without a tool call') },
      })
    if (url === '/api/agent-definitions/fresh/model-check')
      return new Promise<Response>((done) => pending.push(done))
    if (url === '/api/agent-definitions/vague/model-check')
      return answer({ detail: 'agent vague names no model to check' }, 409)
    return served(url, [], [local, cloud], answering)
  })
  const wrapper = await shown()
  const checkRow = (name: string) =>
    agent(wrapper, name)
      .findAll('p')
      .filter((p) => p.text().startsWith('Model check'))
  const row = (name: string) => checkRow(name).map((p) => p.text().replace(/\s+/g, ' '))
  const toned = (name: string, tone: string) =>
    checkRow(name).flatMap((p) => p.findAll(tone).map((part) => part.text()))
  const rows = ['fresh', 'good', 'bad', 'paid'].map(row)
  const tones = [toned('good', '.text-foreground'), toned('bad', '.text-destructive')]

  await (await action(agent(wrapper, 'fresh'), 'Test model fresh')).trigger('click')
  await flushPromises()
  const during = row('fresh')
  const disabled = (await action(agent(wrapper, 'fresh'), 'Test model fresh')).attributes(
    'data-disabled',
  )
  for (const done of pending) done(answer(result(true, '')))
  await flushPromises()
  await (await action(agent(wrapper, 'vague'), 'Test model vague')).trigger('click')
  await flushPromises()

  expect(rows).toStrictEqual([
    ['Model check: not checked'],
    ['Model check: passes, 2m ago'],
    ['Model check: fails, 2m ago, answered without a tool call'],
    [],
  ])
  expect(tones).toStrictEqual([['passes'], ['fails']])
  expect(agent(wrapper, 'paid').text()).not.toContain('Test model')
  expect(sent.filter((s) => s.method === 'POST').map((s) => s.url)).toStrictEqual([
    '/api/agent-definitions/fresh/model-check',
    '/api/agent-definitions/vague/model-check',
  ])
  expect(during).toStrictEqual(['Model check: checking'])
  expect(disabled).toBeDefined()
  expect(
    (await action(agent(wrapper, 'fresh'), 'Test model fresh')).attributes('data-disabled'),
  ).toBeUndefined()
  expect(agent(wrapper, 'vague').text()).toContain('agent vague names no model to check')
})

// CF-473-R1, R2: an agent whose model check failed, or whose ticket is parked on a usage limit,
// says so in its status and ranks before the idle ones.
test('an_agent_that_cannot_run_says_why_and_ranks_first', async () => {
  const parked: AgentDefinition = { ...coder, name: 'parked' }
  const shownList: AgentList = {
    ...list([writer, coder, parked]),
    checks: {
      coder: {
        runtime: 'opencode',
        connection: '',
        model: '',
        passed: false,
        problem: 'it wrote no file',
        at: 1_790_000_000,
      },
    },
    last: {
      parked: {
        run: 'r1',
        repository: 'sample',
        id: 'CF-3',
        stage: 'build',
        at: 1_790_000_000,
        outcome: 'usage limit',
        until: 4_000_000_000,
      },
    },
  }
  stubFetch((url) => (url === '/api/agent-definitions' ? answer(shownList) : served(url, [])))

  const wrapper = await shown()

  const names = wrapper
    .findAll('[role="listitem"][aria-label]')
    .map((card) => card.attributes('aria-label'))
    .filter((name) => ['writer', 'coder', 'parked'].includes(name ?? ''))
  expect(agent(wrapper, 'coder').text()).toContain('Check failed')
  expect(agent(wrapper, 'parked').text()).toContain('usage limit')
  expect(agent(wrapper, 'writer').text()).toContain('Idle')
  expect(names).toStrictEqual(['coder', 'parked', 'writer'])
})

// CF-472-R1: the agents are one column the page's width bounds, so a long name or model id
// truncates on a phone: a list of Items in an ItemGroup, one row each.
test('the_agent_cards_shrink_to_a_phone_width', async () => {
  stubFetch((url) => served(url, [writer]))

  const wrapper = await shown()

  const list = agent(wrapper, 'writer').element.closest('[data-slot="item-group"]')
  expect(list?.getAttribute('role')).toBe('list')
})

// CF-479-R3: the Name field keeps a name within the 40 characters the board takes.
test('the_name_field_keeps_a_name_within_40_characters', async () => {
  stubFetch((url) => served(url, [writer]))
  const wrapper = await shown()

  await button(wrapper, 'New agent').trigger('click')
  await button(agent(wrapper, 'writer'), 'Edit writer').trigger('click')

  const limits = wrapper.findAll('input[name="name"]').map((input) => input.attributes('maxlength'))
  expect(limits).toStrictEqual(['40', '40'])
})

// CF-480-R1: one action at a time on an agent; a removal mid-check left its result behind.
test('a_card_locks_its_actions_while_its_model_is_tested', async () => {
  const local: AgentDefinition = { ...spare, name: 'local', connection: 'near', model: 'm-1' }
  const near: ListedConnection = {
    name: 'near',
    kind: 'lm-studio',
    base_url: 'http://localhost:1234',
    key_env: '',
    key_set: false,
    here: true,
  }
  const status: ConnectionStatus = {
    connections: [
      {
        name: 'near',
        answers: true,
        models: [{ id: 'm-1', context: null, loaded: null }],
        problem: '',
      },
    ],
    local: [],
    reach: {},
  }
  const pending: ((response: Response) => void)[] = []
  const sent = stubFetch((url) => {
    if (url === '/api/agent-definitions/local/model-check')
      return new Promise<Response>((done) => pending.push(done))
    return served(url, [local], [near], status)
  })
  const wrapper = await shown()
  const card = () => agent(wrapper, 'local')
  const locked = async () => {
    const controls = [
      button(card(), 'Edit local'),
      button(card(), 'Pause local'),
      await action(card(), 'Test model local'),
      await action(card(), 'Remove local'),
    ]
    return controls.map(
      (control) =>
        control.attributes('disabled') !== undefined ||
        control.attributes('aria-disabled') === 'true',
    )
  }

  await (await action(card(), 'Test model local')).trigger('click')
  await flushPromises()
  const during = await locked()
  await button(card(), 'Pause local').trigger('click')
  await flushPromises()
  const patches = sent.filter((request) => request.method === 'PATCH')
  for (const done of pending)
    done(
      answer({
        runtime: 'claude',
        connection: 'near',
        model: 'm-1',
        passed: true,
        problem: '',
        at: 1,
      }),
    )
  await flushPromises()

  expect(during).toStrictEqual([true, true, true, true])
  expect(patches).toStrictEqual([])
  expect(await locked()).toStrictEqual([false, false, false, false])
})

// CF-480-R2: the attention order (CF-373) waits while the owner points at the cards.
test('the_cards_keep_their_order_while_pointed_at', async () => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] })
  const named = ['a', 'b', 'c'].map((name) => ({ ...spare, name }))
  let doing: AgentList['doing'] = {}
  stubFetch((url) =>
    url === '/api/agent-definitions' ? answer(list(named, doing)) : served(url, []),
  )
  const wrapper = await shown()
  const order = () =>
    wrapper.findAll('[role="listitem"][aria-label]').map((card) => card.attributes('aria-label'))
  const grid = present(
    agent(wrapper, 'a').element.closest('[data-slot="item-group"]'),
    'the agent list',
  )

  grid.dispatchEvent(new Event('pointerenter'))
  doing = { c: { state: 'over limit', repository: 'sample', id: 'CF-4' } }
  await vi.advanceTimersByTimeAsync(3000)
  await flushPromises()
  const pointed = order()
  grid.dispatchEvent(new Event('pointerleave'))
  await flushPromises()

  expect(pointed).toStrictEqual(['a', 'b', 'c'])
  expect(order()).toStrictEqual(['c', 'a', 'b'])
})

// CF-480-R3: a pause is a change of status, said as one.
test('pausing_and_resuming_are_announced', async () => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] })
  let current: AgentDefinition = writer
  stubFetch((url) => (url === '/api/agent-definitions' ? answer(list([current])) : served(url, [])))
  const wrapper = await shown()
  const region = wrapper.get('[role="status"]')

  current = { ...writer, paused_at: 1_790_000_000 }
  await vi.advanceTimersByTimeAsync(3000)
  await flushPromises()
  const paused = region.text()
  current = writer
  await vi.advanceTimersByTimeAsync(3000)
  await flushPromises()

  expect(paused).toBe('writer paused')
  expect(region.text()).toBe('writer resumed')
})

// CF-480-R4, R5: a paused agent reads paused whatever it holds, with the day of an older pause.
test('a_paused_agent_says_paused_with_its_date', async () => {
  const seconds = (...at: [number, number, number, number, number]) =>
    new Date(...at).getTime() / 1000
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(seconds(2026, 9, 16, 12, 0) * 1000)
  const held = { ...writer, paused_at: seconds(2026, 9, 14, 9, 30) }
  const resting = { ...coder, paused_at: seconds(2026, 9, 16, 8, 15) }
  stubFetch((url) =>
    url === '/api/agent-definitions'
      ? answer(
          list([held, resting], {
            writer: { state: 'over limit', repository: 'sample', id: 'CF-4' },
          }),
        )
      : served(url, []),
  )
  const wrapper = await shown()

  expect(said(wrapper, 'writer')).toContain('Paused 14 Oct 09:30')
  expect(said(wrapper, 'writer')).not.toContain('over limit')
  expect(said(wrapper, 'coder')).toContain('Paused 08:15')
})

// CF-480-R8: as a card's buttons carry their agent's name.
test('a_connection_s_buttons_name_it', async () => {
  stubFetch((url) => served(url, [], [local], checked))
  const wrapper = await shown(CONNECTIONS)

  const names = connection(wrapper, 'local')
    .findAll('button:not([data-slot="collapsible-trigger"])')
    .map((b) => b.text().replace(/\s+/g, ' ').trim())
  expect(names).toStrictEqual(['Edit local', 'Remove local'])
})

// CF-480-R9: localhost and 127.0.0.1 are the same server on this machine.
test('found_servers_are_counted_and_known_ones_left_out', async () => {
  const studio: ListedConnection = { ...local, name: 'studio', base_url: 'http://127.0.0.1:1234' }
  stubFetch((url) =>
    served(url, [], [studio], {
      connections: [{ name: 'studio', answers: true, models: [], problem: '' }],
      local: [
        { kind: 'lm-studio', base_url: 'http://localhost:1234', state: 'answers', models: [] },
        { kind: 'ollama', base_url: 'http://localhost:11434', state: 'answers', models: [] },
      ],
      reach: {},
    }),
  )
  const wrapper = await shown(CONNECTIONS)

  const found = wrapper.get('section[aria-labelledby="found-heading"]')
  expect(found.get('h2').text().replace(/\s+/g, ' ')).toBe('Found on this machine, 1')
  expect(found.findAll('.font-mono').map((address) => address.text())).toStrictEqual([
    'http://localhost:11434',
  ])
  // The owner: its own section beside Connections, not a Card inside it, its servers an Item list.
  expect([
    found.element.parentElement?.closest('section'),
    found.findAll('[data-slot="item-group"] > [data-slot="card"]').length,
  ]).toStrictEqual([null, 1])
})

// CF-480-R10: the owner's answer in brd.md, btn-primary everywhere, two while a form is open.
test('the_main_actions_are_primary_buttons', async () => {
  stubFetch((url) => served(url, [], [], NOTHING))
  const wrapper = await shown()

  const opener = button(wrapper, 'New agent')
  await opener.trigger('click')
  const agentSubmit = wrapper.get('form[aria-label="New agent"] button[type="submit"]')
  await router.push(CONNECTIONS)
  await button(wrapper, 'New connection').trigger('click')
  const connectionSubmit = wrapper.get('form[aria-label="New connection"] button[type="submit"]')

  expect([opener, agentSubmit, connectionSubmit].map((b) => variantOf(b))).toStrictEqual([
    'default',
    'default',
    'default',
  ])
})

/** The mock's team, in order: writer (spec, build), drafter (spec), builder, heavy (build),
 * reviewer (review). */
function team(names: [string, string[]][]): AgentDefinition[] {
  return names.map(([name, roles]) => ({ ...coder, name, runtime: 'claude', roles }))
}
const MOCK: [string, string[]][] = [
  ['writer', ['spec', 'build']],
  ['drafter', ['spec']],
  ['builder', ['build']],
  ['heavy', ['build']],
  ['reviewer', ['review']],
]

/** Each Run order table as its heading and numbered rows. */
function runOrder(wrapper: VueWrapper): string[][] {
  const section = present(
    wrapper.findAll('section').find((s) => s.find('h2').text().startsWith('Run order')),
    'the Run order section',
  )
  return section
    .findAll('[data-run-order]')
    .map((column) => [
      column.get('h3').text().trim(),
      ...column
        .findAll('tbody tr')
        .map((row) => `${row.get('td:nth-child(1)').text()} ${row.get('td:nth-child(2)').text()}`),
    ])
}

// CF-915-R4: one list per column any agent works, its agents numbered in agents.json's order.
test('the_agents_page_shows_each_column_s_run_order', async () => {
  stubFetch((url) => served(url, team(MOCK)))

  const wrapper = await shown()

  expect(runOrder(wrapper)).toStrictEqual([
    ['Spec', '1 writer', '2 drafter'],
    ['Build', '1 writer', '2 builder', '3 heavy'],
    ['Review', '1 reviewer'],
  ])
})

// A 768 px window beside the sidebar leaves each of three columns too narrow for an agent's name,
// which then breaks mid-word: the lists stand side by side from lg on, stacked below it.
test('the_run_order_lists_stand_side_by_side_only_from_lg', async () => {
  stubFetch((url) => served(url, team(MOCK)))

  const wrapper = await shown()
  const grid = present(wrapper.find('[data-run-order]').element.parentElement, 'the lists grid')

  expect([...grid.classList]).toEqual(expect.arrayContaining(['grid-cols-1', 'lg:grid-cols-3']))
  expect([...grid.classList]).not.toContain('md:grid-cols-3')
})

// CF-915-R5: Move up posts the column and direction, the ends' buttons are disabled, and a
// refused move shows its reason.
test('an_agent_is_moved_in_its_column_from_the_agents_page', async () => {
  const sent: { url: string; body: unknown }[] = []
  let refuse = false
  stubFetch((url, init) => {
    if (init?.method === 'POST') {
      sent.push({ url, body: JSON.parse(init.body as string) })
      return refuse
        ? answer({ detail: 'heavy is already first in build' }, 409)
        : answer({ notice: 'Moved heavy up in build', undo: 'u1' })
    }
    return served(url, team(MOCK))
  })
  const wrapper = await shown()
  const named = (label: string) =>
    present(
      wrapper.findAll('button').find((b) => b.attributes('aria-label') === label),
      label,
    )

  expect(named('Move writer up in build').attributes('disabled')).toBeDefined()
  expect(named('Move heavy down in build').attributes('disabled')).toBeDefined()
  expect(named('Move heavy up in build').attributes('disabled')).toBeUndefined()
  await named('Move heavy up in build').trigger('click')
  await flushPromises()
  refuse = true
  await named('Move builder up in build').trigger('click')
  await flushPromises()

  expect(sent).toStrictEqual([
    { url: '/api/agent-definitions/heavy/move', body: { column: 'build', direction: 'up' } },
    { url: '/api/agent-definitions/builder/move', body: { column: 'build', direction: 'up' } },
  ])
  expect(wrapper.text()).toContain('heavy is already first in build')
})

// CF-1208: two tabs, one for what runs (agents, with Claude Code's as read-only sources) and one
// for where it runs (connections, then the servers found).
const claudeFile = (name: string, place: string, n = 0) => ({
  name,
  description: `${name} of ${place}`,
  model: '',
  tools: [],
  place,
  path: `/${place}/${name}${String(n)}.md`,
})

function withClaude(agents: object[]) {
  return (url: string) =>
    url === '/api/claude-agents' ? answer({ agents, unread: [] }) : served(url, [writer])
}

test('the_agents_tab_holds_agents_and_claude_code_agents_only', async () => {
  stubFetch(withClaude([claudeFile('reviewer', 'global')]))

  const wrapper = await shown()

  expect(wrapper.find('#agents-heading').exists()).toBe(true)
  expect(wrapper.find('#claude-agents-heading').exists()).toBe(true)
  expect(wrapper.find('#connections-heading').exists()).toBe(false)
  const tabs = wrapper.findAll('[role="tablist"] a')
  expect(tabs.map((tab) => [tab.text(), tab.attributes('href')])).toStrictEqual([
    ['Agents', '/agents'],
    ['Connections', '/agents?tab=connections'],
  ])
  expect(tabs.map((tab) => tab.attributes('aria-current'))).toStrictEqual(['page', undefined])
})

test('the_connections_tab_holds_connections_only', async () => {
  stubFetch(withClaude([claudeFile('reviewer', 'global')]))

  const wrapper = await shown(CONNECTIONS)

  expect(wrapper.find('#connections-heading').exists()).toBe(true)
  expect(wrapper.find('#agents-heading').exists()).toBe(false)
  expect(wrapper.find('#claude-agents-heading').exists()).toBe(false)
  expect(
    wrapper.findAll('[role="tablist"] a').map((tab) => tab.attributes('aria-current')),
  ).toStrictEqual([undefined, 'page'])
})

test('a_claude_code_agent_a_closer_copy_overrides_says_so', async () => {
  stubFetch(
    withClaude([claudeFile('ticket-worker', 'global'), claudeFile('ticket-worker', 'repo')]),
  )

  const wrapper = await shown()
  const rows = wrapper
    .get('#claude-agents-heading')
    .element.closest('section')
    ?.querySelectorAll('[data-slot="item"]')

  expect([...(rows ?? [])].map((row) => row.textContent)).toStrictEqual([
    expect.stringContaining('overridden by repo'),
    expect.not.stringContaining('overridden'),
  ])
})

test('claude_code_agents_are_paged_ten_to_a_page', async () => {
  const twelve = Array.from({ length: 12 }, (_, n) => claudeFile(`agent-${String(n)}`, 'global', n))
  stubFetch(withClaude(twelve))

  const wrapper = await shown()
  const section = wrapper.get('#claude-agents-heading').element.closest('section')

  expect(section?.querySelectorAll('[data-slot="item"]')).toHaveLength(10)
  expect(wrapper.get('nav[aria-label="Pages of Claude Code agents"]').text()).toContain(
    '1 to 10 of 12',
  )
})

test('a_connections_models_are_a_count_that_opens_to_the_list', async () => {
  stubFetch((url) => served(url, [], [local], checked))

  const wrapper = await shown(CONNECTIONS)
  const models = connection(wrapper, 'local').get('[data-slot="collapsible"]')

  expect(models.get('[data-slot="collapsible-trigger"]').text()).toBe('2 models')
  expect(models.attributes('data-state')).toBe('closed')
  expect(models.text()).toContain('qwen3-coder')
})

test('a_found_server_has_add_beside_its_name_and_models_behind_a_count', async () => {
  stubFetch((url) =>
    served(url, [], [], {
      connections: [],
      local: [
        {
          kind: 'lm-studio',
          base_url: 'http://localhost:1234',
          state: 'answers',
          models: [
            { id: 'one', context: null, loaded: null },
            { id: 'two', context: null, loaded: null },
            { id: 'three', context: null, loaded: null },
          ],
        },
      ],
      reach: {},
    }),
  )

  const wrapper = await shown(CONNECTIONS)
  const found = wrapper.get('section[aria-labelledby="found-heading"]')
  const title = found.get('[data-found-title]')

  expect(title.text()).toContain('LM Studio')
  expect(title.get('button').text()).toContain('Add')
  expect(found.get('[data-slot="collapsible-trigger"]').text()).toBe('3 models')
  expect(found.text()).not.toContain('models: ')
})

// CF-1303: one Scorers table under the agents, only while a repository defines a scorer, and
// nothing on the Connections tab.
const scored = (url: string) =>
  url === '/api/scorers'
    ? answer({
        scorers: [
          {
            repository: 'sample',
            name: 'ran-tests',
            question: 'Did the session run the tests?',
            stage: '',
            sample: 1,
            threshold: 10,
            week: { yes: 3, no: 1, unclear: 0, pass_rate: 0.75 },
            month: { yes: 3, no: 1, unclear: 0, pass_rate: 0.75 },
            ticket: 'CF-9',
          },
        ],
      })
    : served(url, [writer])

test('the_agents_tab_lists_scorers_in_one_table_when_a_repository_defines_one', async () => {
  stubFetch(scored)

  const wrapper = await shown()

  const table = wrapper.get('section[aria-labelledby="scorers-heading"] table')
  expect(table.get('[data-week]').text()).toBe('75%')
  expect(table.get('td:nth-child(6)').text()).toBe('CF-9')
  expect(wrapper.findAll('[aria-labelledby="scorers-heading"]')).toHaveLength(1)
})

test('without_a_scorer_the_page_has_no_scorers_table_and_the_connections_tab_none_either', async () => {
  stubFetch((url) => served(url, [writer]))
  const plain = await shown()
  expect(plain.find('#scorers-heading').exists()).toBe(false)
  plain.unmount()

  stubFetch(scored)
  const connections = await shown(CONNECTIONS)
  expect(connections.find('#scorers-heading').exists()).toBe(false)
})

// A form that opens takes the keyboard to its first field; closing it returns the keyboard to the
// button that opened it. The header is real here: focus is only meaningful on the page's own nodes.
async function shownWithHeader(address: string): Promise<DOMWrapper<HTMLElement>> {
  document.body.innerHTML = '<div id="header-controls"></div>'
  router = memoryRouter([
    { path: '/agents', component: AgentsPage },
    { path: '/:rest(.*)*', component: { render: () => null } },
  ])
  await router.push(address)
  page = mount(AgentsPage, {
    attachTo: document.body,
    global: { plugins: [router], provide: provideBoard() },
  })
  await flushPromises()
  return new DOMWrapper(document.body)
}

// A pointer click focuses the button it presses; a synthetic one does not.
async function click(opener: { element: Element; trigger: (event: string) => Promise<void> }) {
  ;(opener.element as HTMLElement).focus()
  await opener.trigger('click')
}

const POSTED = (url: string, init: RequestInit | undefined) =>
  init?.method === 'POST' ? answer({ notice: 'Added x', undo: null }) : served(url, [])

test('new_agent_focuses_its_name_and_add_and_cancel_return_to_the_button', async () => {
  stubFetch(POSTED)
  const screen = await shownWithHeader('/agents')
  const opener = button(screen, 'New agent')

  await click(opener)
  await flushPromises()
  const name = screen.get('form[aria-label="New agent"] input[name="name"]')
  const opened = document.activeElement
  await button(screen, 'Cancel').trigger('click')
  await flushPromises()
  const cancelled = document.activeElement
  await click(opener)
  await screen.get('form[aria-label="New agent"] input[name="name"]').setValue('x')
  await screen.get('form[aria-label="New agent"]').trigger('submit')
  await validated()

  expect(opened).toBe(name.element)
  expect(cancelled).toBe(opener.element)
  expect(screen.find('form[aria-label="New agent"]').exists()).toBe(false)
  expect(document.activeElement).toBe(opener.element)
})

test('new_connection_focuses_its_name_and_add_and_cancel_return_to_the_button', async () => {
  stubFetch(POSTED)
  const screen = await shownWithHeader(CONNECTIONS)
  const opener = button(screen, 'New connection')

  await click(opener)
  await flushPromises()
  const name = screen.get('form[aria-label="New connection"] input[name="name"]')
  const opened = document.activeElement
  await button(screen, 'Cancel').trigger('click')
  await flushPromises()
  const cancelled = document.activeElement
  await click(opener)
  await screen.get('form[aria-label="New connection"] input[name="name"]').setValue('x')
  await screen.get('form[aria-label="New connection"]').trigger('submit')
  await validated()

  expect(opened).toBe(name.element)
  expect(cancelled).toBe(opener.element)
  expect(screen.find('form[aria-label="New connection"]').exists()).toBe(false)
  expect(document.activeElement).toBe(opener.element)
})

test('cancelling_a_found_servers_form_returns_to_its_add_button', async () => {
  stubFetch((url) =>
    url === '/api/connection-status'
      ? answer({
          connections: [],
          local: [
            { kind: 'lm-studio', base_url: 'http://localhost:1234', state: 'answers', models: [] },
          ],
          reach: {},
        })
      : served(url, []),
  )
  const screen = await shownWithHeader(CONNECTIONS)
  const found = screen.get('section[aria-labelledby="found-heading"]')
  const opener = button(found, 'Add LM Studio')

  await click(opener)
  await flushPromises()
  await button(screen, 'Cancel').trigger('click')
  await flushPromises()

  expect(document.activeElement).toBe(opener.element)
})

// docs/design.md: the primary action is the header's last control, one per screen.
test('the_connections_tab_has_new_connection_as_its_headers_last_and_only_primary', async () => {
  stubFetch((url) => served(url, [], [local]))
  const screen = await shownWithHeader(CONNECTIONS)

  const last = document.getElementById('header-controls')?.lastElementChild
  const primaries = screen.findAll(PRIMARY).map((b) => b.text().trim())
  const section = screen.get('section[aria-labelledby="connections-heading"]')

  expect(last?.textContent.trim()).toBe('New connection')
  expect(last && variantOf(last)).toBe('default')
  expect(primaries).toStrictEqual(['New connection'])
  expect(section.findAll('button').map((b) => b.text().trim())).not.toContain('New connection')
})
