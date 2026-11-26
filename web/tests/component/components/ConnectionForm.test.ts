import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import type { ConnectionDraft, Kind } from '@/lib/connections'
import ConnectionForm from '@/components/ConnectionForm.vue'

const KINDS: Kind[] = [
  {
    kind: 'openrouter',
    label: 'OpenRouter',
    base_url: 'https://openrouter.ai/api',
    key: 'required',
  },
  {
    kind: 'codex-login',
    label: 'Codex login (ChatGPT)',
    base_url: 'https://chatgpt.com/backend-api/codex',
    key: 'login',
  },
  { kind: 'lm-studio', label: 'LM Studio', base_url: 'http://localhost:1234', key: 'none' },
]

function form(kind: string) {
  const start: ConnectionDraft = { name: 'c', kind, base_url: '', key_env: '' }
  return mount(ConnectionForm, {
    props: { name: 'Add', start, kinds: KINDS, submit: 'Save', error: '', busy: false },
  })
}

// CF-1320-R7
test('a_codex_login_connection_reads_no_key_and_is_not_said_to_be_on_this_machine', () => {
  const view = form('codex-login')

  const text = view.text()

  expect(view.find('input[name="key_env"]').exists()).toBe(false)
  expect(text).toContain('Empty: https://chatgpt.com/backend-api/codex')
  expect(text).toContain('only a codex agent takes it')
  expect(text).not.toContain('on this machine only')
})

test('a_local_connection_is_still_said_to_be_on_this_machine_only', () => {
  expect(form('lm-studio').text()).toContain('Empty: http://localhost:1234; on this machine only')
  expect(form('openrouter').find('input[name="key_env"]').exists()).toBe(true)
})

test('a_form_that_opens_focuses_its_name', () => {
  const start: ConnectionDraft = { name: '', kind: 'lm-studio', base_url: '', key_env: '' }
  const view = mount(ConnectionForm, {
    attachTo: document.body,
    props: { name: 'New', start, kinds: KINDS, submit: 'Add', error: '', busy: false },
  })

  expect(document.activeElement).toBe(view.get('input[name="name"]').element)
  view.unmount()
})
