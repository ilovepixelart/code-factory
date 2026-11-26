// @vitest-environment happy-dom
// CF-1229: the Branch property names the branch the board knows the ticket is worked on, while
// the ticket's own `branch:` is empty.

import { afterEach, expect, test, vi } from 'vitest'
import { form, view } from '../../test/ticketForm'

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

const shown = (header: string, branch?: string) => {
  const base = view as { ticket: Record<string, unknown> }
  return { ...base, ticket: { ...base.ticket, branch: header }, branch }
}

async function branchField(header: string, branch?: string) {
  const { page } = await form(shown(header, branch))
  const input = page.get('input[name="branch"]').element as HTMLInputElement
  const read = { value: input.value, placeholder: input.placeholder }
  page.unmount()
  return read
}

test('an_empty_branch_names_the_worktree_s_branch', async () => {
  expect(await branchField('', 'ticket/cf-1205')).toEqual({
    value: '',
    placeholder: 'ticket/cf-1205 (auto)',
  })
})

test('a_branch_the_board_does_not_know_is_set_by_agents', async () => {
  expect((await branchField('', '')).placeholder).toBe('set by agents')
  expect((await branchField('')).placeholder).toBe('set by agents')
})

test('the_header_s_branch_is_the_value', async () => {
  expect((await branchField('fix/login', 'fix/login')).value).toBe('fix/login')
})
