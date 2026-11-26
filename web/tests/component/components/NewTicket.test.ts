// CF-364: the new ticket dialog opens blank on the first repository, its description follows the
// type's template until the person writes in it, and Create sends every field, closing only once
// the board took it (docs/ui.md, Frontend rules).

import { PRIMARY } from '../../support/button'
import { enableAutoUnmount, flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { clear, notice } from '@/lib/notice'
import { answer, spiedBoard, stubFetch } from '../../support/board'
import { present } from '../../support/present'
import { INLINE, escape, isOpen, named } from '../../support/overlay'
import NewTicket from '@/components/NewTicket.vue'
import { addTag, tagsOf, validated } from '../../support/form'

enableAutoUnmount(afterEach)

const TEMPLATES: Record<string, string> = {
  feature: '## Why\n',
  bug: '## Steps\n',
  refactor: '## Shape\n',
  docs: '## What is wrong now\n',
}

function board(
  repositories: string[] = ['sample', 'second'],
  create: () => Response | Promise<Response> = () => answer({ repository: 'sample', id: 'CF-9' }),
  template: (type: string) => Response | Promise<Response> = (type) =>
    answer({ text: TEMPLATES[type] }),
) {
  return stubFetch((url, init) => {
    if (init?.method === 'POST') return create()
    if (url === '/api/repositories') return answer(repositories)
    return template(url.split('/').at(-1) ?? '')
  })
}

type Open = (preset?: { repository?: string; parent?: string }) => Promise<void>

async function opened(preset?: Parameters<Open>[0]) {
  const { live, provide } = spiedBoard()
  const wrapper = mount(NewTicket, { global: { provide, stubs: INLINE }, attachTo: document.body })
  await (wrapper.vm as unknown as { open: Open }).open(preset)
  await flushPromises()
  return { wrapper, live }
}

async function reopen(wrapper: VueWrapper, preset?: { repository?: string; parent?: string }) {
  await (wrapper.vm as unknown as { open: Open }).open(preset)
  await flushPromises()
}

const valueOf = (wrapper: VueWrapper, selector: string) =>
  (wrapper.get(selector).element as HTMLInputElement).value

afterEach(() => {
  vi.unstubAllGlobals()
  clear()
  document.body.innerHTML = ''
})

describe('opening the dialog', () => {
  // CF-571: a read the board does not answer leaves no unhandled failure behind.
  test('opening_while_the_board_does_not_answer_still_opens_the_form', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))),
    )
    const { provide } = spiedBoard()
    const wrapper = mount(NewTicket, {
      global: { provide, stubs: INLINE },
      attachTo: document.body,
    })

    const opening = await (wrapper.vm as unknown as { open: () => Promise<void> }).open().then(
      () => 'opened',
      () => 'failed',
    )
    await flushPromises()

    expect([opening, isOpen(wrapper)]).toEqual(['opened', true])
  })

  // CF-1201-R2: the stage is the board's to set from the evidence, so the form offers none.
  test('the_form_offers_no_stage', async () => {
    board()
    const { wrapper } = await opened()

    expect(wrapper.find('select[name="stage"]').exists()).toBe(false)
    wrapper.unmount()
  })

  test('opening_lists_the_repositories_and_picks_the_first', async () => {
    board()
    const { wrapper } = await opened()

    expect(isOpen(wrapper)).toBe(true)
    expect(wrapper.findAll('#new-repository option').map((o) => o.text())).toEqual([
      'sample',
      'second',
    ])
    expect(valueOf(wrapper, '#new-repository')).toBe('sample')
  })

  // CF-817-R1: opened for a parent, the form holds its id and chooses its repository.
  test('opening_for_a_parent_fills_parent_and_repository', async () => {
    board()
    const { provide } = spiedBoard()
    const wrapper = mount(NewTicket, {
      global: { provide, stubs: INLINE },
      attachTo: document.body,
    })
    const open = (wrapper.vm as unknown as { open: (preset?: object) => Promise<void> }).open

    await open({ repository: 'second', parent: 'CF-7' })
    await flushPromises()

    expect([valueOf(wrapper, '#new-repository'), valueOf(wrapper, '#new-parent')]).toEqual([
      'second',
      'CF-7',
    ])
  })

  test('the_description_starts_as_the_template_of_the_default_type', async () => {
    const sent = board()
    const { wrapper } = await opened()

    expect(sent.map((s) => s.url)).toContain('/api/repositories/sample/templates/feature')
    expect(valueOf(wrapper, '#new-description')).toBe('## Why\n')
  })

  test('no_template_is_read_while_no_repository_is_chosen', async () => {
    const sent = board()
    const { wrapper } = await opened()

    await (wrapper.vm as unknown as { open: () => Promise<void> }).open()
    await flushPromises()

    expect(sent.map((s) => s.url).filter((url) => url.includes('/templates/'))).toEqual([
      '/api/repositories/sample/templates/feature',
      '/api/repositories/sample/templates/feature',
    ])
  })

  test('opening_again_starts_blank', async () => {
    board()
    const { wrapper } = await opened()
    await wrapper.get('input[name="title"]').setValue('Half typed')
    await addTag(wrapper.get('#new-labels'), 'ui')

    await (wrapper.vm as unknown as { open: () => Promise<void> }).open()
    await flushPromises()

    expect(valueOf(wrapper, 'input[name="title"]')).toBe('')
    expect(tagsOf(wrapper.get('#new-labels'))).toEqual([])
  })
})

describe('the description template', () => {
  // CF-822-R4: docs is offered as a type, and choosing it fills the docs template.
  test('the_form_offers_a_docs_type_and_fills_its_template', async () => {
    board()
    const { wrapper } = await opened()

    await wrapper.get('#new-type').setValue('docs')
    await flushPromises()

    expect(wrapper.findAll('#new-type option').map((o) => o.text())).toContain('Docs')
    expect(valueOf(wrapper, '#new-description')).toBe('## What is wrong now\n')
  })

  test('a_new_type_brings_its_template_while_the_description_is_untouched', async () => {
    board()
    const { wrapper } = await opened()

    await wrapper.get('#new-type').setValue('bug')
    await flushPromises()

    expect(valueOf(wrapper, '#new-description')).toBe('## Steps\n')
  })

  test('a_written_description_stays_when_the_type_changes', async () => {
    board()
    const { wrapper } = await opened()

    await wrapper.get('#new-description').setValue('My own words')
    await wrapper.get('#new-type').setValue('bug')
    await flushPromises()

    expect(valueOf(wrapper, '#new-description')).toBe('My own words')
  })

  test('a_template_arriving_for_a_type_no_longer_chosen_is_dropped', async () => {
    let late: (response: Response) => void = () => undefined
    board(undefined, undefined, (type) =>
      type === 'bug'
        ? new Promise<Response>((resolve) => (late = resolve))
        : answer({ text: TEMPLATES[type] }),
    )
    const { wrapper } = await opened()

    await wrapper.get('#new-type').setValue('bug')
    await wrapper.get('#new-type').setValue('refactor')
    await flushPromises()
    late(answer({ text: TEMPLATES.bug }))
    await flushPromises()

    expect(valueOf(wrapper, '#new-description')).toBe('## Shape\n')
  })
})

describe('creating the ticket', () => {
  test.each(['', '   '])(
    'an_empty_title_%j_is_refused_in_the_page_and_nothing_is_sent',
    async (typed) => {
      const sent = board()
      const { wrapper, live } = await opened()

      await wrapper.get('input[name="title"]').setValue(typed)
      await wrapper.get('form[aria-label="New ticket"]').trigger('submit')
      await validated()

      const field = wrapper.get('input[name="title"]')
      const refusal = wrapper.get('[role="alert"]')
      expect(refusal.text()).toBe('Give the ticket a title')
      expect(field.attributes('aria-invalid')).toBe('true')
      expect(field.attributes('aria-describedby')).toContain(refusal.attributes('id'))
      expect(wrapper.get('form').attributes('novalidate')).toBeDefined()
      expect(field.attributes('aria-required')).toBe('true')
      expect(document.activeElement).toBe(field.element)
      expect(sent.filter((s) => s.method === 'POST')).toEqual([])
      expect(live.refresh).not.toHaveBeenCalled()
      expect(isOpen(wrapper)).toBe(true)
    },
  )

  test('the_title_refusal_goes_once_a_title_is_typed', async () => {
    board()
    const { wrapper } = await opened()
    await wrapper.get('form[aria-label="New ticket"]').trigger('submit')
    await validated()
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)

    await wrapper.get('input[name="title"]').setValue('Fix')
    await validated()

    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.get('input[name="title"]').attributes('aria-invalid')).toBeUndefined()
  })

  test('create_sends_every_field_and_closes_the_dialog', async () => {
    const sent = board()
    const { wrapper, live } = await opened()

    await wrapper.get('input[name="title"]').setValue('Fix the login')
    await wrapper.get('#new-priority').setValue('high')
    await addTag(wrapper.get('#new-labels'), 'ui')
    await addTag(wrapper.get('#new-labels'), 'auth')
    await wrapper.get('form[aria-label="New ticket"]').trigger('submit')
    await validated()

    expect(sent.filter((s) => s.method === 'POST')).toEqual([
      {
        method: 'POST',
        url: '/api/tickets',
        body: {
          repository: 'sample',
          title: 'Fix the login',
          description: '## Why\n',
          type: 'feature',
          priority: 'high',
          due: '',
          labels: 'ui, auth',
          assignee: '',
          blocked: '',
          parent: '',
          blocked_by: '',
          budget: '',
          branch: '',
          tests: '',
          e2e: '',
          pages: '',
          caused_by: '',
          parallel: '',
          source: '',
        },
      },
    ])
    expect(isOpen(wrapper)).toBe(false)
    expect(live.refresh).toHaveBeenCalledTimes(1)
  })

  // CF-810-R3: the links, budget and patterns an edit sets go out with Create.
  test('create_sends_the_links_budget_and_patterns', async () => {
    const sent = board()
    const { wrapper } = await opened()

    const fields = ['#new-parent', '#new-blocked_by', '#new-budget', '#new-tests', '#new-e2e']
    expect(fields.filter((field) => !wrapper.find(field).exists())).toEqual([])
    await wrapper.get('input[name="title"]').setValue('Child')
    await wrapper.get('#new-parent').setValue('CF-1')
    await wrapper.get('#new-blocked_by').setValue('CF-2, CF-3')
    await wrapper.get('#new-budget').setValue('5')
    await wrapper.get('#new-tests').setValue('tests/a.rs')
    await wrapper.get('#new-e2e').setValue('web/e2e/a.spec.ts')
    await wrapper.get('form[aria-label="New ticket"]').trigger('submit')
    await validated()

    const body = sent.find((s) => s.method === 'POST')?.body as Record<string, string>
    expect([body.parent, body.blocked_by, body.budget, body.tests, body.e2e]).toEqual([
      'CF-1',
      'CF-2, CF-3',
      '5',
      'tests/a.rs',
      'web/e2e/a.spec.ts',
    ])
  })

  test('a_refused_ticket_keeps_the_dialog_open_and_shows_why', async () => {
    board(undefined, () => answer({ detail: 'a title is required' }, 400))
    const { wrapper } = await opened()

    await wrapper.get('input[name="title"]').setValue('Fix')
    await wrapper.get('form[aria-label="New ticket"]').trigger('submit')
    await validated()

    expect(isOpen(wrapper)).toBe(true)
    expect(wrapper.get('form [role="alert"]').text()).toBe('a title is required')
  })

  test('create_is_disabled_while_the_ticket_is_sent', async () => {
    let reply: (response: Response) => void = () => undefined
    board(undefined, () => new Promise<Response>((resolve) => (reply = resolve)))
    const { wrapper } = await opened()
    const create = () =>
      wrapper.get(`form[aria-label="New ticket"] button[type="submit"]:is(${PRIMARY})`)

    await wrapper.get('input[name="title"]').setValue('Fix')
    await wrapper.get('form[aria-label="New ticket"]').trigger('submit')
    await validated()
    const during = create().attributes('disabled')
    // A refusal keeps the sheet open, so the button is there to read once the answer came.
    reply(answer({ detail: 'Refused' }, 409))
    await flushPromises()

    expect(during).toBeDefined()
    expect(create().attributes('disabled')).toBeUndefined()
  })

  test('close_and_cancel_close_the_dialog_without_a_ticket', async () => {
    const sent = board()
    const { wrapper } = await opened()

    await named(wrapper, 'Close').trigger('click')
    const afterClose = isOpen(wrapper)
    await (wrapper.vm as unknown as { open: () => Promise<void> }).open()
    await flushPromises()
    await present(
      wrapper.findAll('button').find((b) => b.text() === 'Cancel'),
      'Cancel',
    ).trigger('click')

    expect(afterClose).toBe(false)
    expect(isOpen(wrapper)).toBe(false)
    expect(sent.filter((s) => s.method === 'POST')).toEqual([])
  })
})

describe('the notice after a create', () => {
  test('a_created_ticket_is_announced_with_its_id', async () => {
    board(undefined, () => answer({ repository: 'sample', id: 'CF-5' }))
    const { wrapper } = await opened()

    await wrapper.get('input[name="title"]').setValue('Fix')
    await wrapper.get('form[aria-label="New ticket"]').trigger('submit')
    await validated()

    expect([notice.text, notice.error, notice.undo]).toEqual(['Created CF-5', false, null])
  })

  test('a_child_ticket_replaces_the_earlier_notice_with_its_own', async () => {
    board(undefined, () => answer({ repository: 'second', id: 'CF-12' }))
    const { wrapper } = await opened()
    notice.text = 'Moved CF-1 to BRD'
    await reopen(wrapper, { repository: 'second', parent: 'CF-7' })

    await wrapper.get('input[name="title"]').setValue('Child')
    await wrapper.get('form[aria-label="New ticket"]').trigger('submit')
    await validated()

    expect(notice.text).toBe('Created CF-12')
  })
})

describe('the draft', () => {
  async function typed() {
    board()
    const { wrapper } = await opened()
    await wrapper.get('input[name="title"]').setValue('Half typed')
    await wrapper.get('#new-description').setValue('My own words')
    return wrapper
  }
  const fields = (wrapper: VueWrapper) => [
    valueOf(wrapper, 'input[name="title"]'),
    valueOf(wrapper, '#new-description'),
  ]

  test('a_dismissed_dialog_reopens_with_the_typed_text', async () => {
    const wrapper = await typed()

    await escape(wrapper)
    await reopen(wrapper)

    expect(fields(wrapper)).toEqual(['Half typed', 'My own words'])
    expect(isOpen(wrapper)).toBe(true)
  })

  test('the_header_close_keeps_the_draft', async () => {
    const wrapper = await typed()

    await named(wrapper, 'Close').trigger('click')
    await reopen(wrapper)

    expect(fields(wrapper)).toEqual(['Half typed', 'My own words'])
  })

  test('a_kept_draft_keeps_its_repository_and_is_not_overwritten_by_the_template', async () => {
    board()
    const { wrapper } = await opened()
    await wrapper.get('#new-repository').setValue('second')
    await wrapper.get('#new-description').setValue('My own words')
    await flushPromises()

    await escape(wrapper)
    await reopen(wrapper)

    expect([valueOf(wrapper, '#new-repository'), valueOf(wrapper, '#new-description')]).toEqual([
      'second',
      'My own words',
    ])
  })

  test('a_created_ticket_leaves_a_blank_form', async () => {
    const wrapper = await typed()

    await wrapper.get('form[aria-label="New ticket"]').trigger('submit')
    await validated()
    await reopen(wrapper)

    expect(fields(wrapper)).toEqual(['', '## Why\n'])
  })

  test('cancel_discards_the_draft', async () => {
    const wrapper = await typed()

    await present(
      wrapper.findAll('button').find((b) => b.text() === 'Cancel'),
      'Cancel',
    ).trigger('click')
    await reopen(wrapper)

    expect(fields(wrapper)).toEqual(['', '## Why\n'])
  })

  test('a_child_opened_after_a_plain_draft_starts_blank_with_its_parent', async () => {
    const wrapper = await typed()

    await escape(wrapper)
    await reopen(wrapper, { repository: 'second', parent: 'CF-7' })

    expect([...fields(wrapper), valueOf(wrapper, '#new-parent')]).toEqual(['', '## Why\n', 'CF-7'])
  })

  test('a_child_of_another_ticket_starts_blank', async () => {
    board()
    const { wrapper } = await opened({ parent: 'CF-7' })
    await wrapper.get('input[name="title"]').setValue('Child of 7')
    await escape(wrapper)

    await reopen(wrapper, { parent: 'CF-8' })

    expect([valueOf(wrapper, 'input[name="title"]'), valueOf(wrapper, '#new-parent')]).toEqual([
      '',
      'CF-8',
    ])
  })

  test('a_child_draft_is_kept_for_the_same_parent', async () => {
    board()
    const { wrapper } = await opened()
    await reopen(wrapper, { parent: 'CF-7' })
    await wrapper.get('input[name="title"]').setValue('Child of 7')
    await escape(wrapper)

    await reopen(wrapper, { parent: 'CF-7' })

    expect(valueOf(wrapper, 'input[name="title"]')).toBe('Child of 7')
  })

  test('the_title_refusal_is_cleared_on_open', async () => {
    board()
    const { wrapper } = await opened()
    await wrapper.get('form[aria-label="New ticket"]').trigger('submit')
    await validated()
    await escape(wrapper)

    await reopen(wrapper)

    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })
})

// The audit's New ticket: only what a ticket needs shows, the repository is the last one used, and
// a created ticket can be opened from its notice and is brought into view on the board.
describe('a lighter new ticket', () => {
  afterEach(() => {
    localStorage.clear()
  })

  test('where_it_goes_and_what_it_is_show_with_the_rest_folded', async () => {
    board()
    const { wrapper } = await opened()
    const fold = wrapper.get('[aria-label="More properties"]')
    const outFront = ['repository', 'type', 'priority', 'labels'].map(
      (key) => wrapper.find(`#new-${key}`).exists() && !fold.find(`#new-${key}`).exists(),
    )

    expect({
      outFront,
      folded: fold.attributes('data-state'),
      dueInFold: fold.find('#new-due').exists(),
    }).toEqual({ outFront: [true, true, true, true], folded: 'closed', dueInFold: true })
  })

  test('the_repository_of_the_last_ticket_is_chosen_next_time', async () => {
    board(undefined, () => answer({ repository: 'second', id: 'CF-9' }))
    const first = await opened()
    await first.wrapper.get('#new-repository').setValue('second')
    await first.wrapper.get('input[name="title"]').setValue('Fix')
    await first.wrapper.get('form[aria-label="New ticket"]').trigger('submit')
    await validated()
    first.wrapper.unmount()

    const { wrapper } = await opened()

    expect(valueOf(wrapper, '#new-repository')).toBe('second')
  })

  test('a_created_ticket_can_be_opened_from_its_notice_and_is_scrolled_into_view', async () => {
    board(undefined, () => answer({ repository: 'sample', id: 'CF-5' }))
    const card = document.createElement('li')
    card.dataset.ticket = 'CF-5'
    const scrolled = vi.fn()
    card.scrollIntoView = scrolled
    document.body.append(card)
    const { wrapper } = await opened()

    await wrapper.get('input[name="title"]').setValue('Fix')
    await wrapper.get('form[aria-label="New ticket"]').trigger('submit')
    await validated()

    expect([notice.text, notice.follow?.label]).toEqual(['Created CF-5', 'Open CF-5'])
    expect(scrolled).toHaveBeenCalled()
  })
})
