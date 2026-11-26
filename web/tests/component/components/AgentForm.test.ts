import { mount } from '@vue/test-utils'
import { afterEach, expect, test, vi } from 'vitest'
import { nextTick } from 'vue'
import type { ContextVersion } from '@/generated/ContextVersion'
import { draftOf, type AgentDraft } from '@/lib/roster'
import AgentForm from '@/components/AgentForm.vue'
import { validated } from '../../support/form'

const NOW = 1_793_790_000

function form(
  options: {
    context?: string
    error?: string
    history?: ContextVersion[]
    restore?: (at: number) => Promise<boolean>
  } = {},
) {
  const start: AgentDraft = { ...draftOf(null), name: 'granite', context: options.context ?? '' }
  return mount(AgentForm, {
    props: {
      name: 'Edit granite',
      start,
      runtimes: ['claude'],
      gaps: {},
      roles: ['spec'],
      connections: [],
      models: {},
      submit: 'Save',
      error: options.error ?? '',
      busy: false,
      history: options.history ?? [],
      now: NOW,
      restore: options.restore,
    },
  })
}

const area = (view: ReturnType<typeof form>) => view.get('textarea[name="context"]')
const count = (view: ReturnType<typeof form>) => view.get('[data-count]')

// CF-1163-R1
test('agent_form_counts_context_characters', async () => {
  const view = form()
  const label = view.get('fieldset:has(textarea[name="context"]) > legend')

  const typed: [string, string, string][] = []
  for (const length of [0, 695, 7200, 7201, 8000, 8001, 8214]) {
    await area(view).setValue('x'.repeat(length))
    typed.push([String(length), count(view).text(), count(view).classes().join(' ')])
  }
  await area(view).setValue('é😀')

  expect(label.text()).toBe('Context')
  expect(area(view).classes()).toContain('font-mono')
  expect(area(view).attributes('data-slot')).toBe('textarea')
  expect(area(view).attributes('maxlength')).toBeUndefined()
  expect(view.text()).toContain(
    "Markdown, given to every run of this agent after the board's instructions. Changes apply from its next run.",
  )
  expect(typed.map(([n, text]) => [n, text])).toEqual([
    ['0', '0 of 8,000 characters'],
    ['695', '695 of 8,000 characters'],
    ['7200', '7,200 of 8,000 characters'],
    ['7201', '7,201 of 8,000 characters'],
    ['8000', '8,000 of 8,000 characters'],
    ['8001', '8,001 of 8,000 characters, 1 over'],
    ['8214', '8,214 of 8,000 characters, 214 over'],
  ])
  const tone = (at: number) => typed[at]?.[2] ?? ''
  expect([tone(0), tone(1), tone(2)].every((c) => c.includes('text-muted-foreground'))).toBe(true)
  expect([tone(3), tone(4)].every((c) => c.includes('text-foreground'))).toBe(true)
  expect([tone(5), tone(6)].every((c) => c.includes('text-destructive'))).toBe(true)
  expect(count(view).text()).toBe('2 of 8,000 characters')
  const described = area(view).attributes('aria-describedby') ?? ''
  expect(described.split(' ').map((id) => view.find(`[id="${id}"]`).exists())).toEqual([true, true])
})

// CF-1163-R2: the form opens with the agent's context and sends it with the save.
test('the_form_opens_with_the_context_and_saves_it', async () => {
  const view = form({ context: '## This model\nKeep each step small.' })

  expect((area(view).element as HTMLTextAreaElement).value).toBe(
    '## This model\nKeep each step small.',
  )
  await area(view).setValue('Shorter.')
  await view.get('form').trigger('submit')
  await validated()

  expect(view.emitted('save')?.[0]?.[0]).toMatchObject({ name: 'granite', context: 'Shorter.' })
})

// CF-1163-R3: a refusal of the context shows under the field, the text kept, the area invalid.
test('a_refused_context_keeps_its_text_and_says_why', async () => {
  const why = "context is 8,214 characters; an agent's context holds at most 8,000"
  const view = form({ context: 'y'.repeat(8214), error: why })

  const refusal = view.get('[data-slot="field-error"]')

  expect(refusal.text()).toBe(why)
  expect(area(view).attributes('aria-invalid')).toBe('true')
  expect(area(view).attributes('aria-describedby')).toContain(refusal.attributes('id'))
  expect((area(view).element as HTMLTextAreaElement).value).toHaveLength(8214)
  expect(view.get('button[type="submit"]').attributes('disabled')).toBeUndefined()
  await view.setProps({ error: 'an agent named coder is defined' })
  expect(area(view).attributes('aria-invalid')).toBeUndefined()
})

// CF-1163-R8: History lists the versions newest first; Restore makes one current in the area.
test('a_restored_version_fills_the_context', async () => {
  const asked: number[] = []
  const history = [
    { at: NOW - 3600, context: 'second' },
    { at: NOW - 7200, context: 'the first words' },
  ]
  const view = form({
    context: 'third',
    history,
    restore: (at) => {
      asked.push(at)
      return Promise.resolve(true)
    },
  })
  const details = view.get('[data-slot="collapsible"][data-history]')

  expect(details.get('[data-slot="collapsible-trigger"]').text()).toBe(
    'History (2 earlier versions)',
  )
  const rows = details.findAll('li')
  expect(rows.map((row) => row.text().split(' characters')[0]?.split(' · ')[1])).toEqual([
    '6',
    '15',
  ])
  await rows[1]?.findAll('button')[0]?.trigger('click')
  expect(details.get('pre').text()).toBe('the first words')
  await rows[1]?.findAll('button')[1]?.trigger('click')
  await nextTick()
  await nextTick()

  expect(asked).toEqual([NOW - 7200])
  expect((area(view).element as HTMLTextAreaElement).value).toBe('the first words')
  expect(rows[1]?.findAll('button')[1]?.text()).toMatch(/^Restore the version of /)
})

// CF-1163-R8: a refused restore leaves the area as it was; no History without versions.
test('a_refused_restore_keeps_the_context', async () => {
  const kept = form({
    context: 'third',
    history: [{ at: NOW - 60, context: 'second' }],
    restore: () => Promise.resolve(false),
  })
  const none = form({ context: 'third' })

  await kept
    .get('[data-slot="collapsible"][data-history] li')
    .findAll('button')[1]
    ?.trigger('click')
  await nextTick()
  await nextTick()

  expect(kept.get('[data-slot="collapsible-trigger"]').text()).toBe('History (1 earlier version)')
  expect((area(kept).element as HTMLTextAreaElement).value).toBe('third')
  expect(none.find('[data-slot="collapsible"][data-history]').exists()).toBe(false)
})

// CF-1163-R8: at 20 versions the line says the oldest go first.
test('a_full_history_says_the_oldest_go_first', () => {
  const history = Array.from({ length: 20 }, (_, n) => ({
    at: NOW - n * 60,
    context: `v${String(n)}`,
  }))

  const view = form({ context: 'now', history })

  expect(view.get('[data-slot="collapsible-trigger"]').text()).toBe(
    'History (20 earlier versions, the oldest dropped first)',
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
})

// CF-1163-R10: Preview shows the server's rendering of the text as typed; tags in it stay text.
test('the_context_preview_shows_the_typed_text_rendered', async () => {
  const typed = '# Steps\n- one\n\n`cargo test`\n\n<script>window.ran = 1</script>'
  const html =
    '<h1>Steps</h1>\n<ul>\n<li>one</li>\n</ul>\n<p><code>cargo test</code></p>\n<p>&lt;script&gt;window.ran = 1&lt;/script&gt;</p>\n'
  const fetch = vi.fn(() => Promise.resolve(new Response(JSON.stringify({ html }))))
  vi.stubGlobal('fetch', fetch)
  const view = form()
  const tab = (name: string) => view.get(`[role="tab"][data-tab="${name}"]`)

  await area(view).setValue(typed)
  await tab('preview').trigger('mousedown', { button: 0 })
  await vi.waitFor(() => {
    expect(view.find('[data-preview] h1').exists()).toBe(true)
  })
  const panel = view.get('[data-preview]')
  const [path, init] = fetch.mock.calls[0] as unknown as [string, RequestInit]

  expect([tab('write').text(), tab('preview').text()]).toEqual(['Write', 'Preview'])
  expect(tab('preview').attributes('aria-selected')).toBe('true')
  expect(path).toBe('/api/agent-context/preview')
  expect(init.method).toBe('POST')
  expect(JSON.parse(init.body as string)).toEqual({ text: typed })
  expect(panel.get('h1').text()).toBe('Steps')
  expect(panel.get('li').text()).toBe('one')
  expect(panel.get('code').text()).toBe('cargo test')
  expect(panel.find('script').exists()).toBe(false)
  expect(panel.text()).toContain('<script>window.ran = 1</script>')
  expect(area(view).attributes('style')).toContain('display: none')

  await tab('write').trigger('mousedown', { button: 0 })
  expect(area(view).attributes('style') ?? '').not.toContain('display: none')
  expect((area(view).element as HTMLTextAreaElement).value).toBe(typed)
  expect(view.find('[data-preview]').exists()).toBe(false)
})

// CF-1163-R10: an empty context previews a line, asking nothing; a refused preview says why.
test('an_empty_or_refused_preview_says_so', async () => {
  const fetch = vi.fn(() =>
    Promise.resolve(new Response(JSON.stringify({ detail: 'owner only' }), { status: 403 })),
  )
  vi.stubGlobal('fetch', fetch)
  const view = form()
  const preview = () =>
    view.get('[role="tab"][data-tab="preview"]').trigger('mousedown', { button: 0 })

  await preview()
  const empty = view.get('[data-preview]').text()
  await view.get('[role="tab"][data-tab="write"]').trigger('mousedown', { button: 0 })
  await area(view).setValue('Some words.')
  await preview()
  await vi.waitFor(() => {
    expect(view.get('[data-preview]').text()).toContain('owner only')
  })

  expect(empty).toBe('Nothing written yet.')
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(view.get('[data-preview] [data-slot="field-error"]').text()).toBe(
    'The preview failed: owner only',
  )
})

test('a_form_that_opens_focuses_its_name', () => {
  const view = mount(AgentForm, {
    attachTo: document.body,
    props: {
      name: 'New agent',
      start: draftOf(null),
      runtimes: ['claude'],
      gaps: {},
      roles: ['spec'],
      connections: [],
      models: {},
      submit: 'Add',
      error: '',
      busy: false,
    },
  })

  expect(document.activeElement).toBe(view.get('input[name="name"]').element)
  view.unmount()
})
