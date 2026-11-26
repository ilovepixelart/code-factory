import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import { defineComponent, h } from 'vue'
import { goldenBoard, provideBoard } from '../../support/board'
import { useLabelColor } from '@/lib/labels'

const board = goldenBoard()

/** The colour `useLabelColor` gives each of `names` on a board listing `labels`. */
function colours(labels: string[], names: string[]): string[] {
  let said: string[] = []
  const probe = defineComponent({
    setup() {
      const colour = useLabelColor()
      said = names.map(colour)
      return () => h('i')
    },
  })
  mount(probe, {
    global: { provide: provideBoard({ ...board, options: { ...board.options, label: labels } }) },
  })
  return said
}

// CF-1079-R2: the labels in name order take the eight chart colours in turn, so eight labels in
// view never share one, and a ninth starts the colours again.
test('labels_in_view_take_different_colours', () => {
  const labels = ['web', 'ui', 'security', 'quality', 'agents', 'ops', 'docs', 'api']

  const said = colours(labels, ['agents', 'api', 'docs', 'web'])

  expect(said).toEqual(['bg-chart-1', 'bg-chart-2', 'bg-chart-3', 'bg-chart-8'])
  expect(new Set(colours(labels, labels)).size).toBe(8)
  expect(colours([...labels, 'zeta'], ['zeta'])).toEqual(['bg-chart-1'])
})
