// CF-481: the Agents page's roster rules on their own, with expected values worked by hand from
// docs/ui.md (the Agents page row): meter tones and texts, the attention order, the words of a
// change, and what the agent form sends.

import { expect, test } from 'vitest'
import type { AgentDefinition } from '../generated/AgentDefinition'
import {
  bodyOf,
  byAttention,
  changesOf,
  draftOf,
  limitsText,
  metersOf,
  takesText,
  tokensLater,
  type AgentList,
  type Doing,
} from './roster'

function agent(name: string, limits: Partial<AgentDefinition> = {}): AgentDefinition {
  return {
    name,
    runtime: 'claude',
    connection: '',
    model: '',
    roles: ['spec'],
    max_tokens: null,
    max_seconds: null,
    ...limits,
  }
}

function list(agents: AgentDefinition[], doing: AgentList['doing'] = {}): AgentList {
  return {
    agents,
    runtimes: ['claude'],
    gaps: {},
    roles: ['spec'],
    doing,
    last: {},
    checks: {},
    starting: true,
    problem: '',
  }
}

function holding(id: string, tokens: number | null, seconds: number): Doing {
  return { state: 'working', repository: 'sample', id, usage: { tokens, seconds } }
}

test('a_meter_reads_its_use_and_tone_from_the_limit', () => {
  const capped = agent('writer', { max_tokens: 2_000_000, max_seconds: 3600 })
  const read = (tokens: number | null, seconds: number) =>
    metersOf(capped, holding('CF-1', tokens, seconds)).map((m) => [m.limit, m.text, m.tone])

  expect(read(1_499_999, 2699)).toStrictEqual([
    ['tokens', '1.4 M of 2 M tokens', 'default'],
    ['time', '44 of 60 min', 'default'],
  ])
  expect(read(1_500_000, 2700)).toStrictEqual([
    ['tokens', '1.5 M of 2 M tokens', 'warning'],
    ['time', '45 of 60 min', 'warning'],
  ])
  expect(read(1_999_999, 3599)).toStrictEqual([
    ['tokens', '1.9 M of 2 M tokens', 'warning'],
    ['time', '59 of 60 min', 'warning'],
  ])
  expect(read(2_000_000, 3600)).toStrictEqual([
    ['tokens', '2 M of 2 M tokens', 'error'],
    ['time', '60 of 60 min', 'error'],
  ])
  expect(read(null, 60)).toStrictEqual([['time', '1 of 60 min', 'default']])
  expect(tokensLater(capped, holding('CF-1', null, 60))).toBe(true)
  expect(tokensLater(capped, holding('CF-1', 10, 60))).toBe(false)

  const small = agent('coder', { max_tokens: 200_000 })
  expect(metersOf(small, holding('CF-1', 150_000, 10)).map((m) => m.text)).toStrictEqual([
    '150 k of 200 k tokens',
  ])
  expect(metersOf(small, holding('CF-1', 999, 10)).map((m) => m.text)).toStrictEqual([
    '999 of 200 k tokens',
  ])
  expect(metersOf(small, undefined)).toStrictEqual([])
  expect(metersOf(agent('free'), holding('CF-1', 999, 10))).toStrictEqual([])
})

test('agents_needing_attention_sort_first', () => {
  const agents = ['a', 'b', 'c', 'd', 'e', 'f', 'g'].map((name) =>
    name === 'c' ? agent(name, { paused_at: 1_790_000_000 }) : agent(name),
  )
  const on = (state: Doing['state']): Doing => ({ state, repository: 'sample', id: 'CF-1' })
  const read = list(agents, { b: on('working'), d: on('waiting'), e: on('over limit') })
  const names = byAttention(read, (name) => name === 'f').map((a) => a.name)

  expect(names).toStrictEqual(['e', 'd', 'f', 'b', 'c', 'a', 'g'])
  expect(byAttention(read, (name) => name === 'e').map((a) => a.name)[0]).toBe('e')
})

test('a_change_is_said_in_words', () => {
  const agents = ['b', 'd', 'e', 'x'].map((name) => agent(name))
  const before = list(agents, {
    d: { state: 'working', repository: 'sample', id: 'CF-3' },
    e: { state: 'working', repository: 'sample', id: 'CF-4' },
    x: { state: 'working', repository: 'sample', id: 'CF-5' },
  })
  const after = list([...agents, agent('new')], {
    b: { state: 'working', repository: 'sample', id: 'CF-2' },
    d: { state: 'waiting', repository: 'sample', id: 'CF-3' },
    e: { state: 'over limit', repository: 'sample', id: 'CF-4' },
    new: { state: 'working', repository: 'sample', id: 'CF-6' },
  })

  expect(changesOf(before, after)).toBe('b started CF-2; d waiting; e over its limit; x idle')
  expect(changesOf(after, after)).toBe('')

  const capped = [agent('b', { max_tokens: 2_000_000, max_seconds: 3600 })]
  const at = (tokens: number, seconds: number) =>
    list(capped, { b: holding('CF-2', tokens, seconds) })
  expect(changesOf(at(1_000_000, 60), at(1_500_000, 60))).toBe('b at 75% of its tokens')
  expect(changesOf(at(1_500_000, 60), at(2_000_000, 2700))).toBe(
    'b at its token limit; b at 75% of its time',
  )
  expect(changesOf(at(1_500_000, 2700), at(1_600_000, 2800))).toBe('')
  expect(changesOf(at(1_000_000, 2700), at(1_000_000, 3600))).toBe('b at its time limit')
  const elsewhere = list(capped, { b: holding('CF-1', 1_000_000, 60) })
  expect(changesOf(elsewhere, at(1_500_000, 60))).toBe('b started CF-2')
})

test('a_draft_sends_its_limits_in_the_units_the_board_keeps', () => {
  const writer = agent('writer', { model: 'm-1', max_tokens: 200_000, max_seconds: 3600 })

  expect(draftOf(null, 'opencode')).toStrictEqual({
    name: '',
    runtime: 'opencode',
    connection: '',
    model: '',
    roles: [],
    types: [],
    labels: '',
    tokens: '',
    minutes: '',
    context: '',
  })
  expect(draftOf(writer)).toMatchObject({
    name: 'writer',
    model: 'm-1',
    tokens: 200_000,
    minutes: 60,
  })
  expect(
    bodyOf({ ...draftOf(writer), name: ' writer ', model: ' m-2 ', tokens: '', minutes: 90 }),
  ).toStrictEqual({
    name: 'writer',
    runtime: 'claude',
    connection: '',
    model: 'm-2',
    roles: ['spec'],
    types: [],
    labels: [],
    max_tokens: null,
    max_seconds: 5400,
    context: '',
  })
  expect(bodyOf({ ...draftOf(writer), minutes: '' })).toMatchObject({
    max_tokens: 200_000,
    max_seconds: null,
  })
  expect(limitsText(writer)).toBe('200,000 tokens · 60 min')
  expect(limitsText(agent('timed', { max_seconds: 1800 }))).toBe('30 min')
  expect(limitsText(agent('free'))).toBe('no token or time limit')
})

// CF-480-R7: a time limit that is not whole minutes reads in seconds, never rounded away.
test('a_limit_under_a_whole_minute_reads_in_seconds', () => {
  expect(
    [20, 90, 60, 3600].map((seconds) => limitsText(agent('timed', { max_seconds: seconds }))),
  ).toStrictEqual(['20 s', '90 s', '1 min', '60 min'])
})

// CF-1273: the types and labels an agent takes, as the form holds and sends them and the card says them.
test('a_draft_sends_the_types_and_labels_an_agent_takes', () => {
  const scribe = agent('scribe', { types: ['docs', 'bug'], labels: ['ui', 'web'] })

  expect(draftOf(scribe)).toMatchObject({ types: ['docs', 'bug'], labels: 'ui, web' })
  expect(bodyOf({ ...draftOf(scribe), types: ['docs'], labels: ' ui ,, api ' })).toMatchObject({
    types: ['docs'],
    labels: ['ui', 'api'],
  })
  expect(bodyOf({ ...draftOf(scribe), types: [], labels: '' })).toMatchObject({
    types: [],
    labels: [],
  })
})

test('a_card_says_what_an_agent_takes_only_when_it_is_limited', () => {
  expect(takesText(agent('free'))).toBeNull()
  expect(takesText(agent('free', { types: [], labels: [] }))).toBeNull()
  expect(takesText(agent('a', { types: ['docs', 'bug'] }))).toBe('Takes only types docs, bug')
  expect(takesText(agent('b', { labels: ['ui'] }))).toBe('Takes only labels ui')
  expect(takesText(agent('c', { types: ['docs'], labels: ['ui', 'web'] }))).toBe(
    'Takes only types docs · labels ui, web',
  )
})
