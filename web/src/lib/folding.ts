// Which columns are folded: an empty column folds, a
// full one opens; a column the person folded or opened keeps that choice, per browser, until
// its count crosses zero, when the choice is dropped and the column follows its cards again.

import { load, save } from './storage'

const CHOICES = 'codeFactoryColumns'
const COUNTS = 'codeFactoryColumnCounts'

export type Choices = Record<string, boolean>

/** The choices still standing for these counts; a count that crossed zero drops its choice. */
export function standing(counts: Record<string, number>): Choices {
  const choices = load<Choices>(CHOICES, {})
  const before = load<Record<string, string>>(COUNTS, {})
  let changed = false
  for (const [stage, count] of Object.entries(counts)) {
    const was = before[stage]
    const now = String(count)
    if (was !== undefined && (was === '0') !== (now === '0') && stage in choices) {
      delete choices[stage]
      changed = true
    }
    before[stage] = now
  }
  save(COUNTS, before)
  if (changed) save(CHOICES, choices)
  return choices
}

/** Whether a column is folded: the person's choice, else folded when empty. */
export function folded(stage: string, count: number, choices: Choices): boolean {
  return stage in choices ? Boolean(choices[stage]) : count === 0
}

/** Fold or open a column, remembered per browser. */
export function toggle(stage: string, count: number): Choices {
  const choices = load<Choices>(CHOICES, {})
  choices[stage] = !folded(stage, count, choices)
  save(CHOICES, choices)
  return choices
}
