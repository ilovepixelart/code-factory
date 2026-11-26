// @vitest-environment happy-dom
// A stage reads as a glyph that fills as the work moves: Spec an empty ring, Build half filled,
// Review three quarters, Merged a filled circle with a check, Released the same in the muted tone.

import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import type { Stage } from '../lib/board'
import StageGlyph from './StageGlyph.vue'

const glyph = (stage: Stage) => mount(StageGlyph, { props: { stage } })

test('each_stage_draws_its_own_shape_named_for_a_screen_reader', () => {
  const shapes = (['spec', 'build', 'review', 'merged', 'released'] as const).map((stage) => {
    const view = glyph(stage)
    const svg = view.get('svg')
    return {
      label: svg.attributes('aria-label'),
      shape: svg.attributes('data-shape'),
      check: view.find('[data-check]').exists(),
    }
  })

  expect(shapes).toEqual([
    { label: 'Spec', shape: 'ring', check: false },
    { label: 'Build', shape: 'half', check: false },
    { label: 'Review', shape: 'three-quarters', check: false },
    { label: 'Merged', shape: 'done', check: true },
    { label: 'Released', shape: 'done', check: true },
  ])
})

test('a_glyph_takes_its_stage_colour_and_a_released_one_the_muted_tone', () => {
  const colours = (['spec', 'build', 'review', 'merged', 'released'] as const).map(
    (stage) =>
      glyph(stage)
        .get('svg')
        .classes()
        .find((name) => name.startsWith('text-')) ?? '',
  )

  expect(colours).toEqual([
    'text-chart-7',
    'text-chart-1',
    'text-chart-4',
    'text-chart-6',
    'text-muted-foreground',
  ])
})

test('a_glyph_that_sits_beside_its_word_hides_from_a_screen_reader', () => {
  const svg = mount(StageGlyph, { props: { stage: 'build', decorative: true } }).get('svg')

  expect([svg.attributes('aria-hidden'), svg.attributes('aria-label')]).toEqual(['true', undefined])
})
