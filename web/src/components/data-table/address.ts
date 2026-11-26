// A data table's sort and filter in the address, beside its page (CF-1191): `<prefix>sort` names a
// column, `<prefix>dir` is `asc` or `desc` and `<prefix>q` holds the filter's words, so a copied link
// and Back return to the same rows in the same order.

import type { LocationQuery, LocationQueryRaw } from 'vue-router'
import type { SortingState } from '@tanstack/vue-table'

function first(value: LocationQuery[string] | undefined): string {
  const one = Array.isArray(value) ? value[0] : value
  return typeof one === 'string' ? one : ''
}

/** The sort the address names for the table, empty when it names none of `columns`. */
export function sortFrom(query: LocationQuery, prefix: string, columns: string[]): SortingState {
  const id = first(query[`${prefix}sort`])
  if (!columns.includes(id)) return []
  return [{ id, desc: first(query[`${prefix}dir`]) !== 'asc' }]
}

/** The filter's words the address holds for the table. */
export function filterFrom(query: LocationQuery, prefix: string): string {
  return first(query[`${prefix}q`])
}

/** The address filtered by `words`, every other key kept and the table's page left out; no words,
 *  no filter key. */
export function filterLink(query: LocationQuery, prefix: string, words: string): LocationQueryRaw {
  const next: LocationQueryRaw = { ...query }
  delete next[`${prefix}page`]
  delete next[`${prefix}q`]
  return words ? { ...next, [`${prefix}q`]: words } : next
}

/** The address sorted by `column`: descending first, flipped when it is the current sort; every
 *  other key kept and the table's page left out, so the new order starts at its first page. */
export function sortLink(
  query: LocationQuery,
  prefix: string,
  column: string,
  current: SortingState,
): LocationQueryRaw {
  const now = current[0]
  const desc = !(now?.id === column && now.desc)
  const next: LocationQueryRaw = { ...query }
  delete next[`${prefix}page`]
  delete next[`${prefix}sort`]
  delete next[`${prefix}dir`]
  return { ...next, [`${prefix}sort`]: column, [`${prefix}dir`]: desc ? 'desc' : 'asc' }
}

/** The order shown: the address's, else the one the rows come in when the caller names it. */
export function sortShown(
  current: SortingState,
  given: [string, 'asc' | 'desc'] | null,
): SortingState[number] | undefined {
  return current[0] ?? (given ? { id: given[0], desc: given[1] === 'desc' } : undefined)
}

/** A header's `aria-sort`: set only on the column the rows are in the order of. */
export function ariaSortOf(
  shown: SortingState[number] | undefined,
  column: string,
): 'ascending' | 'descending' | undefined {
  if (shown?.id !== column) return undefined
  return shown.desc ? 'descending' : 'ascending'
}
