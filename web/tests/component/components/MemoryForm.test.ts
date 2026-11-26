// The server refuses a new entry without a source (`memory::check_new`) whatever its kind, and
// an edit of an existing entry never asks for one (`memory::edited`): the form says so before the
// click, only for the first.

import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import { labelled } from '../../support/form'
import { MEMORY_KINDS, type MemoryKind } from '@/lib/memory'
import MemoryForm from '@/components/MemoryForm.vue'

type MemoryDraft = InstanceType<typeof MemoryForm>['$props']['start']

const start = (kind: MemoryKind, source = ''): MemoryDraft => ({
  kind,
  statement: 'Gate it',
  why: '',
  source,
  guard: '',
})

function form(draft: MemoryDraft, requireSource: boolean) {
  return mount(MemoryForm, {
    props: { name: 'Entry', start: draft, submit: 'Add', error: '', busy: false, requireSource },
  })
}

const submit = (view: ReturnType<typeof form>) => view.get('button[type="submit"]')
const source = (view: ReturnType<typeof form>) => labelled(view, 'Source')

test.each(MEMORY_KINDS.map(([kind]) => kind))(
  'a_new_%s_without_a_source_says_so_and_cannot_be_added',
  async (kind) => {
    const view = form(start(kind), true)

    expect(view.text()).toContain(
      'Required: where the entry comes from, such as a ticket or a file',
    )
    expect(submit(view).attributes('disabled')).toBeDefined()
    await source(view).setValue('   ')
    expect(submit(view).attributes('disabled')).toBeDefined()
    await source(view).setValue('CF-1')
    expect(submit(view).attributes('disabled')).toBeUndefined()
  },
)

test('an_entry_edited_without_a_source_stays_savable_and_shows_no_requirement', () => {
  const view = form(start('rule'), false)

  expect(view.text()).not.toContain('Required')
  expect(submit(view).attributes('disabled')).toBeUndefined()
})
