// CF-1201: the New ticket form and the edit form's properties list one set of property groups in
// the same order and words (docs/ui.md, The kanban); the board's reason for a refused value shows
// in the form, and every typed value stays.

import { flushPromises, mount, RouterLinkStub, type VueWrapper } from '@vue/test-utils'
import { INLINE, isOpen } from '../../support/overlay'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { reactive, ref } from 'vue'
import { clear } from '@/lib/notice'
import { FIELDS, type Field, type TicketView } from '@/lib/ticket'
import { answer, memoryRouter, provideBoard, spiedBoard, stubFetch } from '../../support/board'
import { view as goldenView } from '../../support/ticketForm'
import NewTicket from '@/components/NewTicket.vue'
import { usePressed } from '@/lib/pressed'
import { TICKET_FORM } from '@/components/ticket/context'
import TicketProperties from '@/components/ticket/TicketProperties.vue'
import TicketForm from '@/components/TicketForm.vue'
import { addTag, pickDay, tagsOf, validated } from '../../support/form'

afterEach(() => {
  vi.unstubAllGlobals()
  clear()
  document.body.innerHTML = ''
})

const GROUPS = {
  Planning: ['Type', 'Priority', 'Due', 'Assignee', 'Labels', 'Blocked'],
  Relations: ['Parent', 'Blocked by', 'Caused by'],
  // CF-1206: E2E tests, Unit tests and Parallel are the fold under Code.
  Code: ['Branch', 'Pages', 'E2E tests', 'Unit tests', 'Parallel'],
  Agent: ['Budget'],
  Origin: ['Source'],
}

/** The Properties region's groups (a fieldset each, named by its legend) and the rows under each, as
 *  written: the ticket's aside, or the New ticket dialog's section. */
function layout(wrapper: VueWrapper): Record<string, string[]> {
  return Object.fromEntries(
    wrapper.findAll('[aria-label="Properties"] fieldset').map((group) => [
      group.get('legend').text(),
      group
        .findAll('[data-slot="field"] > [data-slot="field-label"]')
        // A quiet row's control waits hidden under it; the row is named once, by what shows.
        .filter((label) => !label.element.closest('[data-property-editing]'))
        .map((label) => label.text()),
    ]),
  )
}

const viewOf = (ticket: Record<string, string>): TicketView => ({
  ...(goldenView as TicketView),
  ticket,
  repository: 'sample',
  default_budget: null,
})

function properties(ticket: Record<string, string>, errors: Record<string, string> = {}) {
  const model = reactive(
    Object.fromEntries(FIELDS.map((f) => [f, ticket[f] ?? ''])) as Record<Field, string>,
  )
  const save = vi.fn(() => Promise.resolve())
  const wrapper = mount(TicketProperties, {
    props: { id: 'CF-1', view: viewOf(ticket) },
    global: {
      stubs: { RouterLink: RouterLinkStub },
      provide: {
        [TICKET_FORM as symbol]: {
          model,
          save,
          errors: ref(errors),
          busy: ref(false),
          base: ref('/api/tickets/sample/CF-1'),
          refresh: () => Promise.resolve(),
          task: <T>(work: () => Promise<T>) => work(),
          send: () => Promise.resolve(true),
          ...usePressed(),
        },
      },
    },
  })
  return { wrapper, model, save }
}

function board(create: () => Response = () => answer({ notice: 'Created CF-9', undo: null })) {
  return stubFetch((url, init) => {
    if (init?.method === 'POST') return create()
    if (url === '/api/repositories') return answer(['sample', 'second'])
    return answer({ text: '' })
  })
}

async function opened() {
  const { provide } = spiedBoard()
  const wrapper = mount(NewTicket, { global: { provide, stubs: INLINE }, attachTo: document.body })
  await (wrapper.vm as unknown as { open: () => Promise<void> }).open()
  await flushPromises()
  return wrapper
}

describe('the groups of both forms', () => {
  // CF-1201-R4
  test('ticket_forms_share_groups_and_words', async () => {
    board()
    const create = layout(await opened())
    await (await opened()).get('#new-type').setValue('bug')
    const edit = layout(properties({ type: 'bug' }).wrapper)

    expect(Object.keys(create)).toEqual(['Planning', 'Relations', 'Code', 'Agent', 'Origin'])
    expect(Object.keys(edit)).toEqual(Object.keys(create))
    expect(edit).toEqual({ ...GROUPS, Planning: ['Stage', ...GROUPS.Planning] })
  })

  test('the_new_ticket_form_names_the_repository_first_and_has_no_stage', async () => {
    board()
    const wrapper = await opened()
    await wrapper.get('#new-type').setValue('bug')

    // Where it goes and what it is out front, the rest of the groups folded under "More
    // properties" in the shared order.
    const front = wrapper
      .findAll('[data-properties-front] [data-slot="field-label"]')
      .map((label) => label.text())
    expect(front).toEqual(['Repository', 'Type', 'Priority', 'Labels'])
    expect(layout(wrapper)).toEqual({
      ...GROUPS,
      Planning: GROUPS.Planning.filter((row) => !front.includes(row)),
    })
    expect(wrapper.find('select[name="stage"]').exists()).toBe(false)
  })

  test('caused_by_is_a_bug_property_only', async () => {
    board()
    const wrapper = await opened()
    const labels = () => layout(wrapper).Relations

    expect(labels()).toEqual(['Parent', 'Blocked by'])
    await wrapper.get('#new-type').setValue('bug')
    expect(labels()).toEqual(['Parent', 'Blocked by', 'Caused by'])
    expect(layout(properties({ type: 'feature' }).wrapper).Relations).toEqual([
      'Parent',
      'Blocked by',
    ])
  })
})

describe('the words both forms share', () => {
  // The ticket page has its own Links section; the properties group is not a second one.
  test('an_empty_budget_reads_no_budget_in_the_new_ticket_form_as_on_the_ticket', async () => {
    board()
    const wrapper = await opened()

    expect(wrapper.get('#new-budget').attributes('placeholder')).toBe('no budget')
  })

  test('the_new_ticket_description_hint_is_the_ticket_page_hint', async () => {
    board()
    const wrapper = await opened()

    expect(wrapper.get('#new-description').attributes('placeholder')).toBe(
      'What and why. Markdown; lines starting with - [ ] count as a checklist.',
    )
  })
})

describe('the edit form properties', () => {
  // CF-1201-R1
  test('ticket_properties_show_pages_source_caused_by', () => {
    const { wrapper } = properties({
      type: 'bug',
      pages: '/flow, /sessions',
      source: 'flaky:CF-1:9a5200b',
      caused_by: 'CF-3, CF-4',
    })

    expect((wrapper.get('#CF-1-pages').element as HTMLInputElement).value).toBe('/flow, /sessions')
    // Source is read only: a field like the others that cannot be typed in.
    const source = wrapper.get<HTMLInputElement>('#CF-1-source')
    expect([
      source.attributes('data-slot'),
      source.element.readOnly,
      source.element.value,
      wrapper.get('label[for="CF-1-source"]').text(),
    ]).toEqual(['input', true, 'flaky:CF-1:9a5200b', 'Source'])
    expect(wrapper.findAllComponents(RouterLinkStub).map((l) => [l.text(), l.props('to')])).toEqual(
      [
        ['CF-3', '/tickets/sample/CF-3'],
        ['CF-4', '/tickets/sample/CF-4'],
      ],
    )
  })

  test('an_empty_source_reads_none', () => {
    const source = properties({}).wrapper.get<HTMLInputElement>('#CF-1-source')
    expect([source.element.value, source.attributes('placeholder')]).toEqual(['', 'none'])
  })

  // CF-1201-R3
  test('ticket_edit_sets_pages_and_caused_by', async () => {
    const { wrapper, model, save } = properties({ type: 'bug' })

    await wrapper.get('#CF-1-pages').setValue('/flow')
    await wrapper.get('#CF-1-caused_by').setValue('CF-3')

    expect([model.pages, model.caused_by]).toEqual(['/flow', 'CF-3'])
    expect(save.mock.calls).toEqual([['pages'], ['caused_by']])
  })

  test('a_refusal_shows_under_its_field_and_the_text_stays', () => {
    const { wrapper } = properties(
      { type: 'bug', caused_by: 'CF-3, CF-9999' },
      { caused_by: 'no ticket CF-9999' },
    )

    const why = wrapper.get('[role="alert"]')
    expect(why.text()).toBe('no ticket CF-9999')
    expect(
      why.element.previousElementSibling?.contains(wrapper.get('#CF-1-caused_by').element),
    ).toBe(true)
    expect((wrapper.get('#CF-1-caused_by').element as HTMLInputElement).value).toBe('CF-3, CF-9999')
  })

  test('without_a_refusal_no_reason_shows', () => {
    expect(properties({ type: 'bug' }).wrapper.find('[role="alert"]').exists()).toBe(false)
  })
})

describe('the edit form saving', () => {
  const bug = {
    ...(goldenView as { ticket: Record<string, unknown> }),
    ticket: { ...(goldenView as { ticket: Record<string, unknown> }).ticket, type: 'bug' },
  }

  async function edit(refuse: boolean) {
    const bodies: unknown[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string, init?: RequestInit) => {
        if (init?.method === 'PATCH') {
          bodies.push(JSON.parse(init.body as string))
          return Promise.resolve(
            refuse
              ? answer({ detail: 'no ticket CF-9999' }, 400)
              : answer({ notice: 'Saved', undo: null }),
          )
        }
        return Promise.resolve(answer(bug))
      }),
    )
    document.body.innerHTML = '<div id="app"></div>'
    const router = memoryRouter([{ path: '/', component: { template: '<div />' } }])
    const page = mount(TicketForm, {
      attachTo: '#app',
      props: { repository: 'sample', id: 'CF-1', page: true },
      global: {
        plugins: [router],
        provide: provideBoard(),
        stubs: { RouterLink: true, TicketChanges: true },
      },
    })
    await flushPromises()
    return { page, bodies }
  }

  test('a_refused_caused_by_shows_the_reason_under_it_and_keeps_the_text', async () => {
    const { page, bodies } = await edit(true)

    await page.get('#CF-1-caused_by').setValue('CF-9999')
    await flushPromises()

    expect(bodies).toEqual([{ caused_by: 'CF-9999' }])
    expect(page.get('[role="alert"]').text()).toBe('no ticket CF-9999')
    expect((page.get('#CF-1-caused_by').element as HTMLInputElement).value).toBe('CF-9999')
    expect(page.text()).toContain('Not saved')
  })

  test('a_refusal_shows_not_saved_in_the_error_colour', async () => {
    const { page } = await edit(true)
    const footer = (): string =>
      page.get('[data-testid="ticket-footer"] [aria-live]').classes().join(' ')

    await page.get('#CF-1-caused_by').setValue('CF-9999')
    await flushPromises()
    const refused = footer()

    expect(refused).toContain('text-destructive')
    expect(refused).not.toContain('text-foreground')
  })

  test('a_saved_change_shows_saved_in_the_success_colour', async () => {
    const { page } = await edit(false)

    await page.get('#CF-1-caused_by').setValue('CF-3')
    await flushPromises()

    const footer = page.get('[data-testid="ticket-footer"] [aria-live]')
    expect(footer.text()).toBe('Saved')
    expect(footer.classes()).toContain('text-foreground')
  })

  test.each([
    ['empty', ''],
    ['whitespace', '   '],
  ])('a_%s_title_is_refused_restored_and_not_sent', async (_name, typed) => {
    const { page, bodies } = await edit(false)
    const title = page.get('textarea[name="title"]')
    const loadedTitle = (title.element as HTMLTextAreaElement).value

    await title.setValue(typed)
    await flushPromises()

    expect(bodies).toEqual([])
    expect((title.element as HTMLTextAreaElement).value).toBe(loadedTitle)
    expect(page.get('[role="alert"]').text()).toBe('A ticket needs a title.')
    expect(title.attributes('aria-invalid')).toBe('true')
    expect(page.text()).toContain('Not saved')
  })

  test('a_title_edited_to_text_is_sent_and_clears_the_refusal', async () => {
    const { page, bodies } = await edit(false)
    const title = page.get('textarea[name="title"]')
    await title.setValue('')
    await flushPromises()

    await title.setValue('Renamed')
    await flushPromises()

    expect(bodies).toEqual([{ title: 'Renamed' }])
    expect(page.find('[role="alert"]').exists()).toBe(false)
  })

  test('a_saved_value_clears_the_reason', async () => {
    const { page } = await edit(true)
    await page.get('#CF-1-caused_by').setValue('CF-9999')
    await flushPromises()
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string, init?: RequestInit) =>
        Promise.resolve(
          init?.method === 'PATCH' ? answer({ notice: 'Saved', undo: null }) : answer(bug),
        ),
      ),
    )

    await page.get('#CF-1-caused_by').setValue('CF-3')
    await flushPromises()

    expect(page.find('[role="alert"]').exists()).toBe(false)
  })
})

describe('the new ticket form', () => {
  // CF-1201-R2
  test('new_ticket_sets_every_field_the_board_accepts', async () => {
    const sent = board()
    const wrapper = await opened()
    await wrapper.get('#new-type').setValue('bug')
    await flushPromises()

    const typed: Record<string, string> = {
      title: 'Crash',
      priority: 'high',
      assignee: 'alex',
      blocked: 'waiting',
      parent: 'CF-1',
      blocked_by: 'CF-2',
      caused_by: 'CF-3',
      branch: 'fix/crash',
      tests: 'tests/a.rs',
      e2e: 'web/e2e/a.spec.ts',
      pages: '/flow',
      budget: '5',
      parallel: '3',
      source: 'issue 12',
    }
    for (const [name, value] of Object.entries(typed)) {
      await wrapper.get(`[name="${name}"]`).setValue(value)
    }
    await addTag(wrapper.get('#new-labels'), 'ui')
    const due = await pickDay(wrapper.get('#new-due'))
    await wrapper.get('form[aria-label="New ticket"]').trigger('submit')
    await validated()

    const body = sent.find((s) => s.method === 'POST')?.body as Record<string, string>
    expect(body).toEqual({
      repository: 'sample',
      type: 'bug',
      description: '',
      ...typed,
      labels: 'ui',
      due,
    })
    expect(due).toMatch(/^\d{4}-\d{2}-01$/)
  })

  test('a_caused_by_typed_for_a_bug_is_not_sent_once_the_type_is_not_a_bug', async () => {
    const sent = board()
    const wrapper = await opened()
    await wrapper.get('#new-type').setValue('bug')
    await wrapper.get('[name="caused_by"]').setValue('CF-3')
    await wrapper.get('#new-type').setValue('feature')
    await wrapper.get('input[name="title"]').setValue('Not a bug')
    await wrapper.get('form[aria-label="New ticket"]').trigger('submit')
    await validated()

    const body = sent.find((s) => s.method === 'POST')?.body as Record<string, string>
    expect(body.caused_by).toBe('')
  })

  test('a_refused_value_shows_the_reason_in_the_form_and_keeps_every_value', async () => {
    board(() => answer({ detail: 'no ticket CF-9999' }, 400))
    const wrapper = await opened()
    await wrapper.get('#new-type').setValue('bug')
    await wrapper.get('input[name="title"]').setValue('Crash')
    await wrapper.get('[name="caused_by"]').setValue('CF-9999')
    await addTag(wrapper.get('#new-labels'), 'ui')

    await wrapper.get('form[aria-label="New ticket"]').trigger('submit')
    await validated()

    expect(wrapper.get('form [role="alert"]').text()).toBe('no ticket CF-9999')
    expect(isOpen(wrapper)).toBe(true)
    const kept = ['title', 'caused_by'].map(
      (n) => (wrapper.get(`[name="${n}"]`).element as HTMLInputElement).value,
    )
    expect([...kept, tagsOf(wrapper.get('#new-labels'))]).toEqual(['Crash', 'CF-9999', ['ui']])
  })

  test('opening_again_clears_the_reason', async () => {
    board(() => answer({ detail: 'a title is required' }, 400))
    const wrapper = await opened()
    await wrapper.get('form[aria-label="New ticket"]').trigger('submit')
    await validated()
    await (wrapper.vm as unknown as { open: () => Promise<void> }).open()
    await flushPromises()

    expect(wrapper.find('form [role="alert"]').exists()).toBe(false)
  })
})
