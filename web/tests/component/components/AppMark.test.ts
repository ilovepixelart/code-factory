// The product's mark is the owner's factory drawing: terracotta walls, a sawtooth roof, three lit
// windows, a door, a chimney with three puffs of smoke, in literal colours and no letters.

import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import AppMark from '@/components/AppMark.vue'

test('the_mark_is_the_factory_drawing_in_a_32_unit_box', () => {
  const mark = mount(AppMark).get('svg')

  expect(mark.attributes('viewBox')).toBe('0 0 32 32')
  expect(mark.findAll('rect')).toHaveLength(6)
  expect(mark.findAll('path')).toHaveLength(7)
  expect(mark.findAll('circle')).toHaveLength(3)
  expect(mark.findAll('rect[fill="#ffd166"]')).toHaveLength(3)
})

test('the_mark_paints_every_shape_with_a_literal_colour_and_no_style_or_class', () => {
  const mark = mount(AppMark).get('svg')
  const shapes = mark.findAll('rect, path, circle')

  expect(shapes.map((shape) => shape.attributes('fill'))).toSatisfy(
    (fills: (string | undefined)[]) => fills.every((fill) => /^#[0-9a-f]{6}$/.test(fill ?? '')),
  )
  expect(shapes.filter((shape) => shape.attributes('class') ?? shape.attributes('style'))).toEqual(
    [],
  )
})

test('the_mark_holds_no_letters_and_is_hidden_from_assistive_technology', () => {
  const mark = mount(AppMark).get('svg')

  expect(mark.text()).toBe('')
  expect(mark.attributes('aria-hidden')).toBe('true')
})
