// An answer holds its choices or Other's text, never both: picking one side clears the other.

import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import { NOTHING_PICKED, type Asked, type Picking } from '@/lib/questions'
import QuestionChoices from '@/components/QuestionChoices.vue'

const choice = (text: string) => ({ text, recommended: false, reason: '', ticked: false })

function choices(several: boolean) {
  const question: Asked = {
    document: 'uat.md',
    index: 0,
    text: 'Which page?',
    choices: [choice('Flow'), choice('Tickets')],
    several,
  }
  const picked: Picking[] = []
  const view = mount(QuestionChoices, {
    props: {
      question,
      modelValue: NOTHING_PICKED,
      'onUpdate:modelValue': async (next: Picking) => {
        picked.push(next)
        await view.setProps({ modelValue: next })
      },
    },
  })
  return { view, picked }
}

const other = 'input[aria-label="Other answer to Which page?"]'

test('ticking_choices_after_other_drops_its_text', async () => {
  const { view, picked } = choices(true)
  const boxes = () => view.findAll('[role="checkbox"]')

  await view.get(other).setValue('The inbox')
  await boxes()[0]?.trigger('click')
  await boxes()[1]?.trigger('click')

  expect(picked.at(-1)).toEqual({ choices: ['Flow', 'Tickets'], other: null })
  expect(boxes().map((box) => box.attributes('aria-checked'))).toEqual(['true', 'true', 'false'])
})

test('typing_other_drops_the_ticked_choices', async () => {
  const { view, picked } = choices(true)

  await view.findAll('[role="checkbox"]')[0]?.trigger('click')
  await view.get(other).setValue('The inbox')

  expect(picked.at(-1)).toEqual({ choices: [], other: 'The inbox' })
})

test('one_choice_replaces_another_and_other_replaces_both', async () => {
  const { view, picked } = choices(false)
  const radios = () => view.findAll('[role="radio"]')

  await radios()[0]?.trigger('click')
  await radios()[1]?.trigger('click')
  const second = picked.at(-1)
  await radios()[2]?.trigger('click')

  expect(second).toEqual({ choices: ['Tickets'], other: null })
  expect(picked.at(-1)).toEqual({ choices: [], other: '' })
  expect(radios().map((radio) => radio.attributes('aria-checked'))).toEqual([
    'false',
    'false',
    'true',
  ])
})

// A choice whose reason wraps keeps its radio or box beside its first line, not centred on both.
test('a_choice_aligns_its_control_with_its_first_line', () => {
  for (const several of [false, true]) {
    const { view } = choices(several)
    const control = several ? '[role="checkbox"]' : '[role="radio"]'
    const row = view.get(control).element.closest('[data-slot="field"]')

    expect(row?.classList.contains('items-start')).toBe(true)
    expect(view.get(control).classes()).toContain('mt-0.5')
  }
})
