// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import MergedCostSection from '@/components/factory/MergedCostSection.vue'
import type { MergedCost } from '@/lib/factory'

const summary: MergedCost = {
  median: 126.25,
  priced: 2,
  owner_recorded: 3,
  merged: 4,
  estimated: false,
}

function render(value?: MergedCost): string {
  const view = mount(MergedCostSection, { props: { summary: value } })
  const text = view.text()
  view.unmount()
  return text
}

test('only a range with merges shows a cost section', () => {
  expect(render()).toBe('')
  expect(render({ ...summary, merged: 0 })).toBe('')
})

test('known costs show the median along with the measured coverage', () => {
  const text = render(summary)
  expect(text).toContain('Median $126.25')
  expect(text).toContain('2 of 4 merges have complete costs.')
  expect(text).toContain('Owner time recorded for 3.')
  expect(render({ ...summary, estimated: true })).toContain('Estimated median $126.25')
})

test('missing costs show the measured coverage without a median', () => {
  const text = render({ ...summary, median: null, priced: 0 })
  expect(text).not.toContain('Median')
  expect(text).toContain('0 of 4 merges have complete costs.')
})
