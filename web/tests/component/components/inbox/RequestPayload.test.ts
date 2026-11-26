// A permission request's content as it would act: a shell command as code, a call's Markdown
// content rendered as the board renders Markdown, its other fields as a short list, and text that
// is not JSON as code.

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, test, vi } from 'vitest'
import RequestPayload from '@/components/inbox/RequestPayload.vue'

afterEach(() => {
  vi.unstubAllGlobals()
})

/** The payload over a server whose Markdown preview answers `html`, and the texts sent to it. */
async function shown(tool: string, summary: string, html = '<h1>Spec</h1>\n<p>Body</p>\n') {
  const sent: unknown[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      sent.push([url, JSON.parse(init?.body as string)])
      return Promise.resolve(new Response(JSON.stringify({ html }), { status: 200 }))
    }),
  )
  const wrapper = mount(RequestPayload, { props: { tool, summary } })
  await flushPromises()
  return { wrapper, sent }
}

const code = (wrapper: Awaited<ReturnType<typeof shown>>['wrapper']) =>
  wrapper.findAll('[data-slot="code-block-content"]').map((c) => c.element.textContent)
const fields = (wrapper: Awaited<ReturnType<typeof shown>>['wrapper']) =>
  wrapper.findAll('dt').map((dt) => [dt.text(), dt.element.nextElementSibling?.textContent])

test('a_shell_command_shows_as_code_with_its_lines', async () => {
  const { wrapper, sent } = await shown('Bash', 'git status\nuv run pytest')

  expect(code(wrapper)).toEqual(['git status\nuv run pytest'])
  expect(sent).toEqual([])
})

test('a_calls_markdown_content_is_rendered_and_its_other_fields_listed', async () => {
  const call = { name: 'spec', content: '# Spec\n\nBody', ticket: 'CF-2' }
  const { wrapper, sent } = await shown('mcp__code-factory__write_document', JSON.stringify(call))

  expect(sent).toEqual([['/api/agent-context/preview', { text: '# Spec\n\nBody' }]])
  expect(wrapper.find('.typeset h1').text()).toBe('Spec')
  expect(fields(wrapper)).toEqual([
    ['name', 'spec'],
    ['ticket', 'CF-2'],
  ])
  expect(code(wrapper)).toEqual([])
})

test('a_command_field_shows_as_code_and_a_nested_value_as_json', async () => {
  const call = { command: 'ls\n-la', options: { deep: true } }
  const { wrapper } = await shown('Task', JSON.stringify(call))

  expect(code(wrapper)).toEqual(['ls\n-la'])
  expect(fields(wrapper)).toEqual([['options', '{"deep":true}']])
})

// The board cuts a request's text at 300 characters, which leaves its JSON open.
test('a_call_cut_short_is_still_read_and_says_so', async () => {
  const cut = '{"name": "spec", "content": "# Spec\\n\\nThe first part'
  const { wrapper, sent } = await shown('mcp__code-factory__write_document', cut)

  expect(sent).toEqual([['/api/agent-context/preview', { text: '# Spec\n\nThe first part' }]])
  expect(fields(wrapper)).toEqual([['name', 'spec']])
  expect(wrapper.text()).toContain('Cut short')
})

test('text_that_is_not_an_object_shows_as_code', async () => {
  const plain = await shown('Read', 'not json at all')
  const list = await shown('Read', '[1,2]')

  expect([code(plain.wrapper), code(list.wrapper)]).toEqual([
    ['not json at all'],
    ['[\n  1,\n  2\n]'],
  ])
})
