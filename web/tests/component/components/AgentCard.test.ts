import { flushPromises, mount } from '@vue/test-utils'
import { INLINE, openMenu } from '../../support/overlay'
import { expect, test } from 'vitest'
import type { AgentDefinition } from '@/generated/AgentDefinition'
import { answer as confirmAnswer, question } from '@/lib/confirm'
import { answer, stubFetch } from '../../support/board'
import AgentCard from '@/components/AgentCard.vue'
import AgentCardMenu from '@/components/AgentCardMenu.vue'

function card(model = 'recursivesi/flint', local = true) {
  const agent: AgentDefinition = {
    name: 'flint',
    runtime: 'claude',
    connection: local ? 'lmstudio' : '',
    model,
    roles: ['spec'],
    max_tokens: null,
    max_seconds: null,
    paused_at: 1_793_784_556,
  }
  return mount(AgentCard, {
    global: { stubs: INLINE },
    props: {
      agent,
      doing: undefined,
      last: undefined,
      modelCheck: undefined,
      local,
      now: 1_793_790_000,
      runtimes: ['claude'],
      gaps: {},
      roles: ['spec'],
      connections: ['lmstudio'],
      models: {},
      reach: '',
      checking: false,
    },
  })
}

// CF-1078-R1: a paused local agent's card: Resume and Edit as buttons in the row; Check, Test model
// and Remove in the menu, Remove last in the error tone.
test('an_agent_card_shows_two_buttons_and_a_menu', async () => {
  const view = card()
  const row = view.find('[data-actions]')

  const shown = row.findAll(':scope > button:not([data-menu])').map((b) => b.text())
  await openMenu(view, '[data-menu]')
  const items = view.findAll('[role="menuitem"]')

  expect(shown).toEqual(['Resume flint', 'Edit flint'])
  expect(view.get('[data-menu]').attributes('aria-label')).toBe('More actions for flint')
  expect(items.map((b) => b.text())).toEqual(['Check flint', 'Test model flint', 'Remove flint'])
  expect(items.at(-1)?.attributes('data-variant')).toBe('destructive')
  expect(
    row.findAll('[data-slot="button"]:not([data-variant="ghost"]):not([data-menu])'),
  ).toHaveLength(1)
})

// CF-1065-R1: a local agent with no model says it needs one, in the warning tone; one with no
// connection keeps "harness default", and a local agent with a model shows the model.
test('a_local_agent_without_a_model_says_so', () => {
  const missing = card('', true)
  const hosted = card('', false)
  const named = card('qwen/qwen3.8-27b', true)

  const line = (page: ReturnType<typeof card>) => page.findAll('p')[0]
  expect(line(missing)?.text()).toBe('no model: a local connection needs one')
  expect(line(missing)?.classes()).toContain('text-foreground')
  expect(line(hosted)?.text()).toBe('harness default')
  expect(line(named)?.text()).toBe('qwen/qwen3.8-27b')
  for (const page of [missing, hosted, named]) page.unmount()
})

// Owner: the name leads in the sans font, its model under it in mono and muted; an agent with no
// run says so in one muted line of the card, and the menu sits beside Pause and Edit.
test('an_agent_card_reads_name_then_model_and_keeps_its_menu_by_its_buttons', () => {
  const view = card('qwen/qwen3.8-27b', true)

  const model = view.findAll('p')[0]
  const none = view.findAll('p').find((p) => p.text() === 'No runs yet')
  expect(view.get('h3').classes()).not.toContain('font-mono')
  expect(model?.text()).toBe('qwen/qwen3.8-27b')
  expect(model?.classes()).toEqual(expect.arrayContaining(['font-mono', 'text-muted-foreground']))
  expect(none?.classes()).toContain('text-muted-foreground')
  expect(view.find('[data-slot="empty"]').exists()).toBe(false)
  expect(view.get('[data-menu]').classes()).not.toContain('ml-auto')
})

// 2026-11-10 14:05 and 2026-11-05 16:10 UTC.
const CURRENT = 1_794_319_500
const EARLIER = 1_793_895_000

function contextCard(context: string | undefined, receivedAt: number | undefined) {
  const agent: AgentDefinition = {
    name: 'granite',
    runtime: 'pi',
    connection: '',
    model: 'ibm/granite-4.1-8b',
    roles: ['spec', 'build'],
    max_tokens: null,
    max_seconds: null,
    ...(context === undefined ? {} : { context, context_at: CURRENT }),
  }
  const last = {
    run: '7c1e09a4b2d3',
    repository: 'code-factory',
    id: 'CF-1160',
    stage: 'build' as const,
    at: CURRENT + 600,
    outcome: 'finished' as const,
    ...(receivedAt === undefined ? {} : { context_at: receivedAt }),
  }
  return mount(AgentCard, {
    props: {
      agent,
      doing: undefined,
      last,
      modelCheck: undefined,
      local: false,
      now: CURRENT + 3600,
      runtimes: ['pi'],
      gaps: {},
      roles: ['spec', 'build'],
      connections: [],
      models: {},
      reach: '',
      checking: false,
    },
  })
}

// CF-1163-R4
test('agent_card_says_which_version_the_last_run_received', () => {
  const zone = process.env.TZ
  process.env.TZ = 'UTC'
  try {
    const text = 'x'.repeat(694) + '😀'
    const line = (page: ReturnType<typeof contextCard>) =>
      page.find('[data-context]').exists()
        ? page.get('[data-context]').text().replace(/\s+/g, ' ')
        : null

    const pages = [
      contextCard(text, undefined),
      contextCard(text, CURRENT),
      contextCard(text, EARLIER),
      contextCard(undefined, EARLIER),
    ]

    expect(pages.map(line)).toEqual([
      'Context: 695 characters, its next run receives it',
      'Context: 695 characters, last run 7c1e09a4b2d3 (CF-1160 Build) received the version of 10 Nov 14:05',
      'Context: 695 characters, its next run receives it; last run 7c1e09a4b2d3 (CF-1160 Build) received the version of 5 Nov 16:10',
      null,
    ])
    expect(pages[1]?.get('[data-context] .font-mono').text()).toBe('7c1e09a4b2d3')
    expect(pages[0]?.text()).not.toContain(text.slice(0, 20))
    for (const page of pages) page.unmount()
  } finally {
    process.env.TZ = zone
  }
})

// The name heads the card in the sans face, its model under it in mono and the muted tone.
test('the_name_heads_the_card_and_the_model_is_muted_mono_under_it', () => {
  const view = card('recursivesi/flint', false)

  const model = view.findAll('p')[0]

  expect(view.get('h3').text()).toBe('flint')
  expect(view.get('h3').classes()).not.toContain('font-mono')
  expect(model?.text()).toBe('recursivesi/flint')
  expect(model?.classes()).toEqual(expect.arrayContaining(['font-mono', 'text-muted-foreground']))
  view.unmount()
})

// An agent with no run says so as one muted line in the card, not as a centred Empty block.
test('no_runs_yet_is_one_muted_line', () => {
  const view = card()

  const line = view.findAll('p').find((p) => p.text() === 'No runs yet')

  expect(view.find('[data-slot="empty"]').exists()).toBe(false)
  expect(line?.classes()).toContain('text-muted-foreground')
  view.unmount()
})

// The actions menu follows Edit in the row; it is not pushed to the card's far edge.
test('the_actions_menu_sits_beside_edit', () => {
  const view = card()

  const buttons = view.get('[data-actions]').findAll(':scope > button')

  expect(buttons.map((b) => b.attributes('data-menu') !== undefined)).toEqual([false, false, true])
  expect(view.get('[data-menu]').classes()).not.toContain('ml-auto')
  view.unmount()
})

// The card reads as an Item: the agent's icon leads it, and its state and its key's reach are
// badges in the status colours, not loose text.
test('the_card_leads_with_its_icon_and_shows_state_and_reach_as_badges', () => {
  const view = card()

  expect({
    media: view.find('[data-slot="card-header"] svg').exists(),
    badges: view.findAll('[data-slot="badge"]').map((b) => b.text()),
  }).toEqual({
    media: true,
    badges: expect.arrayContaining(['Spec', expect.stringMatching(/^Paused/)]),
  })
  view.unmount()
})

// One rule for every removal: Remove asks first, as Delete on a ticket does; a No sends nothing,
// a Yes sends the DELETE (whose notice still offers Undo).
test('removing_an_agent_asks_first_and_sends_only_on_yes', async () => {
  const sent = stubFetch(() => answer({ notice: 'Removed flint', undo: 'u1' }))
  const view = card()

  view.findComponent(AgentCardMenu).vm.$emit('remove')
  await flushPromises()
  const asked = { ...question, answer: null }
  confirmAnswer(false)
  await flushPromises()
  const afterNo = sent.length
  view.findComponent(AgentCardMenu).vm.$emit('remove')
  await flushPromises()
  confirmAnswer(true)
  await flushPromises()

  expect([asked.title, asked.text, afterNo, sent.map((s) => s.method)]).toEqual([
    'Remove agent',
    'flint',
    0,
    ['DELETE'],
  ])
  view.unmount()
})
