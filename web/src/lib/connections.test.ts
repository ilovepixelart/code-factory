// CF-481: the Agents page's connection rules on their own, with expected values from docs/ui.md
// (the Agents page and Connections rows): what a card says of its connection, what the form
// sends, and which connections are served on this machine.

import { expect, test } from 'vitest'
import {
  connectionBodyOf,
  connectionDraftOf,
  contextText,
  kindLabel,
  needsAttention,
  reachOf,
  type Reach,
  runsHere,
  type ConnectionList,
  type ConnectionStatus,
  type Kind,
  type ListedConnection,
} from './connections'

const KINDS: Kind[] = [
  {
    kind: 'openrouter',
    label: 'OpenRouter',
    base_url: 'https://openrouter.ai/api',
    key: 'required',
  },
  { kind: 'lm-studio', label: 'LM Studio', base_url: 'http://localhost:1234', key: 'none' },
]

function defined(name: string, kind: string, keyEnv = '', keySet = false): ListedConnection {
  // As the server's `runs_here` answers it: a known kind served on this machine.
  const here = ['lm-studio', 'ollama', 'llama-cpp', 'custom'].includes(kind)
  return { name, kind, base_url: 'http://127.0.0.1:1', key_env: keyEnv, key_set: keySet, here }
}

const LIST: ConnectionList = {
  connections: [
    defined('local', 'lm-studio'),
    defined('cloud', 'openrouter', 'OPENROUTER_API_KEY'),
    defined('keyed', 'openrouter', 'OPENROUTER_API_KEY', true),
    defined('odd', 'mystery'),
  ],
  kinds: KINDS,
  problem: '',
}

/** A finished check that says `said` of the agent `coder`'s model. */
function status(said: Reach): ConnectionStatus {
  return { connections: [], local: [], reach: { coder: said } }
}

test('an_agents_reach_is_read_from_its_connection_and_check', () => {
  const reach = (connection: string, checked: ConnectionStatus | null) =>
    reachOf({ name: 'coder', connection }, LIST, checked)

  expect(reach('', status('answers'))).toBe('')
  expect(reach('cloud', null)).toBe('key missing')
  expect(reach('local', null)).toBe('')
  expect(reachOf({ name: 'coder', connection: 'local' }, LIST, status('answers'), true)).toBe(
    'checking',
  )
  expect(reachOf({ name: 'coder', connection: 'cloud' }, LIST, null, true)).toBe('key missing')
  expect(reach('local', status('context 63,999 of 64,000'))).toBe('context 63,999 of 64,000')
  expect(reach('keyed', status('does not answer'))).toBe('does not answer')
  expect(reachOf({ name: 'other', connection: 'local' }, LIST, status('answers'))).toBe('')

  const words = ['', 'checking', 'answers', 'does not answer', 'key missing', 'model not listed']
  expect(
    words.map((word) => needsAttention(word as Parameters<typeof needsAttention>[0])),
  ).toStrictEqual([false, false, false, true, true, true])
  expect(needsAttention('context 63,999 of 64,000')).toBe(true)
})

test('a_connection_draft_and_locality_follow_its_kind', () => {
  expect(
    connectionBodyOf({
      name: ' local ',
      kind: 'lm-studio',
      base_url: ' http://h:1 ',
      key_env: ' K ',
    }),
  ).toStrictEqual({ name: 'local', kind: 'lm-studio', base_url: 'http://h:1', key_env: 'K' })
  expect(connectionDraftOf(null, 'ollama', 'http://localhost:11434')).toStrictEqual({
    name: '',
    kind: 'ollama',
    base_url: 'http://localhost:11434',
    key_env: '',
  })
  expect(kindLabel(KINDS, 'lm-studio')).toBe('LM Studio')
  expect(kindLabel(KINDS, 'mystery')).toBe('mystery')
  expect(contextText({ id: 'qwen', context: 131_072, loaded: null })).toBe('131,072 tokens')
  expect(contextText({ id: 'qwen', context: null, loaded: null })).toBe('')

  expect(runsHere({ connection: 'local' }, LIST)).toBe(true)
  expect(runsHere({ connection: 'cloud' }, LIST)).toBe(false)
  expect(runsHere({ connection: 'odd' }, LIST)).toBe(false)
  expect(runsHere({ connection: 'gone' }, LIST)).toBe(false)
  expect(runsHere({ connection: 'local' }, null)).toBe(false)
})

// CF-529: a run gets the context the server holds the model with, so the row says it.
test('a_model_s_context_says_what_it_is_loaded_with', () => {
  expect(
    [
      { id: 'big', context: 131_072, loaded: 8192 },
      { id: 'idle', context: 131_072, loaded: null },
      { id: 'tiny', context: null, loaded: 4096 },
      { id: 'bare', context: null, loaded: null },
    ].map(contextText),
  ).toStrictEqual(['131,072 tokens, loaded at 8,192', '131,072 tokens', 'loaded at 4,096', ''])
})
