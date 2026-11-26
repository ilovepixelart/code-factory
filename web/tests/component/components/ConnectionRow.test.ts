// CF-1333: a codex-login connection's status says it uses this machine's codex login.

import { flushPromises, mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import { answer as confirmAnswer, question } from '@/lib/confirm'
import type { Checked, Kind, ListedConnection } from '@/lib/connections'
import { answer, stubFetch } from '../../support/board'
import ConnectionRow from '@/components/ConnectionRow.vue'

const KINDS: Kind[] = [
  { kind: 'ollama', label: 'Ollama', base_url: 'http://localhost:11434', key: 'none' },
  {
    kind: 'codex-login',
    label: 'Codex login (ChatGPT)',
    base_url: 'https://chatgpt.com/backend-api/codex',
    key: 'login',
  },
]

function row(kind: string, status: Checked): string {
  const connection: ListedConnection = {
    name: 'c',
    kind,
    base_url: 'http://localhost:11434',
    key_env: '',
    key_set: false,
    here: kind === 'ollama',
  }
  return mount(ConnectionRow, {
    props: { connection, kinds: KINDS, status, checking: false },
  }).text()
}

const answers: Checked = { name: 'c', answers: true, models: [], problem: '' }

test('a_codex_login_that_serves_says_it_uses_the_codex_login', () => {
  expect(row('codex-login', answers)).toContain("uses this machine's codex login")
})

test('a_codex_login_without_a_usable_file_says_why', () => {
  const missing = { ...answers, answers: false, problem: 'no codex login at /x/auth.json' }

  const text = row('codex-login', missing)

  expect(text).toContain('no codex login at /x/auth.json')
  expect(text).not.toContain('uses this machine')
})

test('another_kind_that_answers_still_says_answers', () => {
  const text = row('ollama', answers)

  expect(text).toContain('answers')
  expect(text).not.toContain('codex login')
})

// The key line says a key variable holds no value; the check's problem saying it again is dropped.
test('a_key_not_set_is_said_once', () => {
  const connection: ListedConnection = {
    name: 'cloud',
    kind: 'ollama',
    base_url: 'https://example.com/api',
    key_env: 'CLOUD_KEY',
    key_set: false,
    here: false,
  }
  const status = { ...answers, answers: false, problem: 'CLOUD_KEY is not set' }

  const text = mount(ConnectionRow, {
    props: { connection, kinds: KINDS, status, checking: false },
  }).text()

  expect(text).toContain('key: CLOUD_KEY not set')
  expect(text).not.toContain('is not set')
})

test('a_problem_with_the_key_set_still_shows', () => {
  const connection: ListedConnection = {
    name: 'cloud',
    kind: 'ollama',
    base_url: 'https://example.com/api',
    key_env: 'CLOUD_KEY',
    key_set: true,
    here: false,
  }
  const status = { ...answers, answers: false, problem: 'HTTP 401 from https://example.com' }

  const text = mount(ConnectionRow, {
    props: { connection, kinds: KINDS, status, checking: false },
  }).text()

  expect(text).toContain('HTTP 401 from https://example.com')
})

// Below sm the name, address and key take the whole row and the actions wrap under them, so a
// phone does not cut the address to a few characters beside Edit and Remove.
test('the_actions_wrap_under_the_connection_on_a_phone', () => {
  const view = mount(ConnectionRow, {
    props: {
      connection: {
        name: 'c',
        kind: 'ollama',
        base_url: 'http://localhost:11434',
        key_env: '',
        key_set: false,
        here: true,
      },
      kinds: KINDS,
      status: answers,
      checking: false,
    },
  })

  expect(view.get('[data-slot="item-content"]').classes()).toContain('max-sm:basis-full')
})

// One rule for every removal: it asks first, as Delete on a ticket does, and a No sends nothing.
test('removing_a_connection_asks_first_and_a_no_sends_nothing', async () => {
  const sent = stubFetch(() => answer({ notice: '', undo: null }))
  const view = mount(ConnectionRow, {
    props: {
      connection: {
        name: 'local',
        kind: 'ollama',
        base_url: 'http://localhost:11434',
        key_env: '',
        key_set: false,
        here: true,
      },
      kinds: KINDS,
      status: answers,
      checking: false,
    },
  })

  await view
    .findAll('button')
    .find((b) => b.text().startsWith('Remove'))
    ?.trigger('click')
  const asked = { ...question, answer: null }
  confirmAnswer(false)
  await flushPromises()

  expect([asked.title, asked.text, sent.length]).toEqual(['Remove connection', 'local', 0])
})
