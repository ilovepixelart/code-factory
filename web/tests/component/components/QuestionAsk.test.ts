// A question reads the same everywhere: its topic, Pick one or Pick any, its choices as cards with
// what each means and a preview, Select all for several, and Answer counting what is ticked.

import { flushPromises, mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import type { Asked } from '@/lib/questions'
import QuestionAsk from '@/components/QuestionAsk.vue'

const choice = (text: string, more: Partial<Asked['choices'][number]> = {}) => ({
  text,
  recommended: false,
  reason: '',
  ticked: false,
  ...more,
})

function asked(several: boolean): Asked {
  return {
    document: '',
    index: 0,
    text: 'Which columns?',
    topic: 'Columns',
    several,
    choices: [
      choice('Order', { recommended: true, description: 'Totals add up.' }),
      choice('Item', { preview: 'order,item\n1,Mug' }),
      choice('Day'),
    ],
  }
}

test('the_topic_leads_the_question_and_pick_says_how_many_it_takes', () => {
  const one = mount(QuestionAsk, { props: { asked: asked(false) } })
  const many = mount(QuestionAsk, { props: { asked: asked(true) } })

  expect([one.get('[data-topic]').text(), one.text().includes('Pick one')]).toEqual([
    'Columns',
    true,
  ])
  expect(many.text()).toContain('Pick any')
})

test('a_card_says_what_its_choice_means_and_shows_its_preview_as_code', () => {
  const view = mount(QuestionAsk, { props: { asked: asked(false) } })

  expect(view.text()).toContain('Totals add up.')
  expect(view.get('pre').text()).toBe('order,item\n1,Mug')
})

test('select_all_ticks_every_choice_and_answer_counts_them', async () => {
  const view = mount(QuestionAsk, { props: { asked: asked(true) } })

  await view
    .findAll('button')
    .find((b) => b.text() === 'Select all')
    ?.trigger('click')
  await flushPromises()
  const answer = view.get('[data-answer]')
  await view.get('form').trigger('submit')

  expect(answer.text()).toBe('Answer with 3')
  expect(view.emitted('send')).toEqual([[{ choices: ['Order', 'Item', 'Day'] }]])
})

test('focusing_other_picks_it_in_place_of_the_choices', async () => {
  const view = mount(QuestionAsk, { props: { asked: asked(false) } })
  const radios = () => view.findAll('[role="radio"]').map((r) => r.attributes('aria-checked'))
  const before = radios()

  await view.get('input[aria-label="Other answer to Which columns?"]').trigger('focus')

  expect([before, radios()]).toEqual([
    ['true', 'false', 'false', 'false'],
    ['false', 'false', 'false', 'true'],
  ])
})
