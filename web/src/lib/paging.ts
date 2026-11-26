// A list's page in the address (CF-1191): `<prefix>page` and `<prefix>size`, page 1 and the list's
// own size left out; a number is whole from 1 with no leading zero on both halves.

import { computed, watch, type ComputedRef } from 'vue'
import { useRoute, useRouter, type LocationQuery, type LocationQueryRaw } from 'vue-router'

/** The sizes a person can pick. */
export const SIZES = [10, 25, 50, 100] as const
/** The size of a list that is its page's subject: the owner's answer of 2026-11-10. */
export const LIST_SIZE = 50

export interface Place {
  page: number
  size: number
}

const WHOLE = /^[1-9]\d*$/

function first(value: LocationQuery[string] | undefined): string {
  const one = Array.isArray(value) ? value[0] : value
  return typeof one === 'string' ? one : ''
}

/** The page and size the address names for the list, page 1 and `fallback` for anything else. */
export function fromAddress(query: LocationQuery, prefix: string, fallback: number): Place {
  const page = first(query[`${prefix}page`])
  const size = first(query[`${prefix}size`])
  return {
    page: WHOLE.test(page) ? Number(page) : 1,
    size:
      WHOLE.test(size) && (SIZES as readonly number[]).includes(Number(size))
        ? Number(size)
        : fallback,
  }
}

/** The number of the last page: 1 for a list with no rows. */
export function lastPage(total: number, size: number): number {
  return Math.max(1, Math.ceil(total / size))
}

/** The page numbers to link: the first, the last, the current and its neighbours, `…` between. */
export function numbers(page: number, last: number): (number | '…')[] {
  const kept = [...new Set([1, page - 1, page, page + 1, last])]
    .filter((n) => n >= 1 && n <= last)
    .sort((a, b) => a - b)
  return kept.flatMap((n, i) => (i > 0 && n - (kept[i - 1] ?? n) > 1 ? ['…' as const, n] : [n]))
}

/** The rows a page shows, in words: `11 to 20 of 247`. */
export function rangeText(page: number, size: number, total: number): string {
  const from = (page - 1) * size + 1
  return `${String(from)} to ${String(Math.min(total, page * size))} of ${String(total)}`
}

/** The address of a page of the list: every other key kept, page 1 and `fallback` left out. */
export function linkTo(
  query: LocationQuery,
  prefix: string,
  page: number,
  size: number,
  fallback: number,
): LocationQueryRaw {
  const next: LocationQueryRaw = { ...query }
  delete next[`${prefix}page`]
  delete next[`${prefix}size`]
  if (page > 1) next[`${prefix}page`] = String(page)
  if (size !== fallback) next[`${prefix}size`] = String(size)
  return next
}

/** The page's slice of `rows`; past the last page, the last. */
export function slicePage<T>(rows: T[], page: number, size: number): T[] {
  const shown = Math.min(page, lastPage(rows.length, size))
  return rows.slice((shown - 1) * size, shown * size)
}

export interface Paged<T> {
  rows: ComputedRef<T[]>
  total: ComputedRef<number>
  page: ComputedRef<number>
  size: ComputedRef<number>
}

/** A list paged in the browser over rows it already holds (`null` until they are read). A page
 *  past the last shows the last, and the address is replaced with its number. */
export function usePaged<T>(all: () => T[] | null, prefix = '', fallback = LIST_SIZE): Paged<T> {
  const route = useRoute()
  const router = useRouter()
  const place = computed(() => fromAddress(route.query, prefix, fallback))
  const total = computed(() => all()?.length ?? 0)
  const page = computed(() => Math.min(place.value.page, lastPage(total.value, place.value.size)))
  watch(
    [page, () => place.value.page, () => all() !== null],
    ([shown, , read]) => {
      if (read && shown !== place.value.page && first(route.query[`${prefix}page`]) !== '')
        void router.replace({
          query: linkTo(route.query, prefix, shown, place.value.size, fallback),
        })
    },
    { immediate: true },
  )
  return {
    rows: computed(() => slicePage(all() ?? [], page.value, place.value.size)),
    total,
    page,
    size: computed(() => place.value.size),
  }
}
