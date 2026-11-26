// CF-364: docs/ui.md (The kanban), the ticket's properties beside its content: each row puts its
// label left of its field, an empty one says what empty means, a code value carries its whole
// value as the tooltip, and each saves itself when changed.

import { ArrowRight01Icon } from '@hugeicons/core-free-icons'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { describe, expect, test, vi } from 'vitest'
import { reactive, ref } from 'vue'
import { FIELDS, type Field, type TicketView } from '@/lib/ticket'
import { addTag, pickDay, tagsOf } from '../../../support/form'
import { draws } from '../../../support/icons'
import { usePressed } from '@/lib/pressed'
import { TICKET_FORM } from '@/components/ticket/context'
import TicketProperties from '@/components/ticket/TicketProperties.vue'

function viewWith(defaultBudget: number | null): TicketView {
  return {
    ticket: {},
    repository: 'sample',
    checklist: [],
    summary: { gate: null, verdict: '', capture: null, not_proven: [] },
    current_stage: 'build',
    work_done: false,
    runs: [],
    spent: 0,
    cost: { total: null, review: null, cache_read: null, turns: null },
    budget: null,
    default_budget: defaultBudget,
    halted: '',
    month_budget: null,
    questions: [],
    documents: [],
    plan: null,
    link: null,
    titles: {},
    stages_by_id: {},
    linked: {},
    description_html: '',
    check: null,
    check_log: '',
    checks_configured: true,
    checking: false,
    activity: [],
  }
}

function properties(
  values: Partial<Record<Field, string>> = {},
  defaultBudget: number | null = null,
) {
  const model = reactive(
    Object.fromEntries(FIELDS.map((f) => [f, values[f] ?? ''])) as Record<Field, string>,
  )
  const save = vi.fn(() => Promise.resolve())
  const wrapper = mount(TicketProperties, {
    props: { id: 'CF-1', view: viewWith(defaultBudget) },
    global: {
      provide: {
        [TICKET_FORM as symbol]: {
          model,
          save,
          errors: ref({}),
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

const field = (wrapper: VueWrapper, key: string) =>
  wrapper.get(`#CF-1-${key}`).element as HTMLInputElement

describe('the ticket properties', () => {
  // The owner: the rail fits the sheet at any width. A text input is 20 characters wide unless told
  // otherwise, which pushed the Labels row 44 px past a 720 px sheet; it asks for one character
  // and grows into the row.
  test('the_labels_input_asks_for_no_more_width_than_its_row', () => {
    const { wrapper } = properties()

    expect(field(wrapper, 'labels').getAttribute('size')).toBe('1')
  })

  test('each_row_names_its_property_left_of_its_field', () => {
    const { wrapper } = properties()

    const shown = wrapper
      .findAll('aside fieldset > [data-slot="field"] > label')
      .map((s) => s.text())
    expect(shown).toEqual([
      'Stage',
      'Type',
      'Priority',
      'Due',
      'Assignee',
      'Labels',
      'Blocked',
      'Parent',
      'Blocked by',
      'Branch',
      'Pages',
      'Budget',
      'Source',
    ])
  })

  // CF-1206: the test patterns and parallel attempts, still read by the board, sit folded under Code.
  test('tests_and_parallel_are_folded_under_code', () => {
    const { wrapper } = properties()

    const folded = wrapper.get('[data-slot="collapsible"][aria-label="More code settings"]')

    expect(folded.attributes('data-state')).toBe('closed')
    const shown = folded
      .findAll('[data-slot="field"] > label')
      .filter((label) => !label.element.closest('[data-property-editing]'))
    expect(shown.map((s) => s.text())).toEqual(['E2E tests', 'Unit tests', 'Parallel'])
  })

  // A fold reads as a control, not as an empty section: a chevron and the state it is in.
  test('the_fold_trigger_shows_a_chevron_and_whether_it_is_open', () => {
    const { wrapper } = properties()

    const trigger = wrapper.get(
      '[aria-label="More code settings"] > [data-slot="collapsible-trigger"]',
    )

    expect(trigger.text()).toBe('Tests and parallel')
    expect(trigger.attributes('aria-expanded')).toBe('false')
    expect(draws(trigger.get('svg').element, ArrowRight01Icon)).toBe(true)
  })

  // CF-1206: a fold does not hide a value set: it opens when one of its fields has one.
  test('the_fold_opens_when_a_folded_field_is_set', () => {
    const { wrapper } = properties({ parallel: '2' })

    expect(
      wrapper
        .get('[data-slot="collapsible"][aria-label="More code settings"]')
        .attributes('data-state'),
    ).toBe('open')
  })

  test('each_field_shows_the_value_being_edited', () => {
    const { wrapper } = properties({
      stage: 'review',
      type: 'bug',
      priority: 'high',
      labels: 'ui',
      parent: 'CF-0',
      branch: 'fix/login',
      budget: '4',
    })

    expect(
      ['stage', 'type', 'priority', 'parent', 'branch', 'budget'].map(
        (key) => field(wrapper, key).value,
      ),
    ).toEqual(['review', 'bug', 'high', 'CF-0', 'fix/login', '4'])
    expect(tagsOf(wrapper.get('#CF-1-labels'))).toEqual(['ui'])
  })

  test('an_empty_property_says_what_empty_means', () => {
    const { wrapper } = properties()

    expect(
      ['labels', 'assignee', 'blocked', 'blocked_by', 'parent', 'branch', 'e2e', 'tests'].map(
        (key) => field(wrapper, key).placeholder,
      ),
    ).toEqual([
      'none',
      'unassigned',
      'not blocked',
      'none',
      'none',
      'set by agents',
      'none',
      'none',
    ])
    expect(wrapper.get('#CF-1-due').text()).toBe('none')
  })

  // CF-1081-R2, CF-1089-R1: the empty choice names the stage the evidence holds, Build in this view.
  test('the_stage_choices_start_with_auto_and_use_the_stage_names', () => {
    const { wrapper } = properties()

    expect(wrapper.findAll('#CF-1-stage option').map((o) => o.text())).toEqual([
      'Build (auto)',
      'Spec',
      'Build',
      'Review',
      'Merged',
    ])
  })

  // CF-1108-R3
  test('the_properties_set_the_parallel_attempts', async () => {
    const { wrapper, model, save } = properties()

    const parallel = wrapper.get('#CF-1-parallel')
    expect(parallel.findAll('option').map((o) => o.text())).toEqual(['1', '2', '3', '4'])
    expect(parallel.attributes('title')).toBe(
      'One Build run; 2 to 4 start that many, each by another agent',
    )
    await parallel.setValue('3')

    expect(model.parallel).toBe('3')
    expect(save).toHaveBeenCalled()
  })

  test('the_priority_choices_start_with_none_and_the_type_has_no_empty_choice', () => {
    const { wrapper } = properties()

    expect(wrapper.findAll('#CF-1-priority option').map((o) => o.text())).toEqual([
      'none',
      'Urgent',
      'High',
      'Medium',
      'Low',
    ])
    expect(wrapper.findAll('#CF-1-type option').map((o) => o.text())).toEqual([
      'Feature',
      'Bug',
      'Refactor',
      'Upgrade',
      'Hotfix',
      'Docs',
    ])
  })

  test('linked_ticket_ids_and_code_values_are_set_in_mono', () => {
    const { wrapper } = properties()
    const mono = (key: string) => field(wrapper, key).classList.contains('font-mono')

    expect(
      ['blocked_by', 'parent', 'branch', 'e2e', 'tests', 'labels', 'assignee'].map(mono),
    ).toEqual([true, true, true, true, true, false, false])
  })

  test('a_code_value_carries_its_whole_value_as_the_tooltip', () => {
    const { wrapper } = properties({ branch: 'feature/CF-1-a-very-long-branch-name' })

    expect(field(wrapper, 'branch').title).toBe('feature/CF-1-a-very-long-branch-name')
    expect(field(wrapper, 'e2e').hasAttribute('title')).toBe(false)
  })

  test('the_budget_placeholder_names_the_configured_default', () => {
    expect(field(properties({}, 2.5).wrapper, 'budget').placeholder).toBe('from config: $2.50')
  })

  test('a_configured_default_of_zero_is_still_named', () => {
    expect(field(properties({}, 0).wrapper, 'budget').placeholder).toBe('from config: $0.00')
  })

  test('without_a_configured_default_the_budget_reads_no_budget', () => {
    expect(field(properties({}, null).wrapper, 'budget').placeholder).toBe('no budget')
  })

  // aria-labelledby outranks aria-label in the accessible name (W3C accname 1.2, step 2B): the
  // remove button names what it does only when nothing labels it by the tag's text.
  test('a_label_s_remove_button_is_named_for_removing_it', () => {
    const { wrapper } = properties({ labels: 'docs' })
    const remove = wrapper.get('button[aria-label="Remove docs"]').element

    expect(remove.getAttribute('aria-labelledby')).toBeNull()
  })

  test('a_typed_value_lands_in_the_form_being_edited', async () => {
    const { wrapper, model } = properties()

    await wrapper.get('#CF-1-assignee').setValue('alex')
    await wrapper.get('#CF-1-budget').setValue('7.5')
    await wrapper.get('#CF-1-priority').setValue('low')

    expect([model.assignee, model.budget, model.priority]).toEqual(['alex', '7.5', 'low'])
  })

  // A typed or chosen property saves on change; Labels saves each tag added and Due each day picked.
  // The read-only Source never saves.
  test('every_property_saves_itself_when_changed', async () => {
    const { wrapper, save } = properties()
    const controls = wrapper.findAll('input, select').filter((c) => c.element.id !== 'CF-1-labels')

    for (const control of controls) await control.trigger('change')
    await flushPromises()
    await addTag(wrapper.get('#CF-1-labels'), 'ui')
    await pickDay(wrapper.get('#CF-1-due'))

    expect(controls).toHaveLength(14)
    expect(save.mock.calls.map((call) => (call as unknown[])[0])).toEqual([
      'stage',
      'type',
      'priority',
      'assignee',
      'blocked',
      'parent',
      'blocked_by',
      'branch',
      'pages',
      'e2e',
      'tests',
      'parallel',
      'budget',
      'labels',
      'due',
    ])
  })
})
