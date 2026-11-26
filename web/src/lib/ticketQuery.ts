// The tickets page's state in the address: filters, lanes, sort and the filter box's text, and
// the links that change one of them. Every link keeps the filter box's text, and the box follows
// the address when it changes (CF-311).

import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { filterPairs, SORTS, toggled, urlOf, type Lanes, type Pairs, type Sort } from './view'

export interface Chip {
  key: string
  value: string
  href: string
}

export interface TicketQuery {
  query: ComputedRef<Pairs>
  lanes: ComputedRef<Lanes>
  sort: ComputedRef<string>
  direction: ComputedRef<string>
  needle: Ref<string>
  chips: ComputedRef<Chip[]>
  clearUrl: ComputedRef<string>
  boardUrl: ComputedRef<string>
  listUrl: ComputedRef<string>
  toggleUrl: (key: string, value: string) => string
  lanesUrl: (value: string) => string
  sortUrl: (column: Sort) => string
}

/** The search text, kept in step with the address's `q` both ways. */
function useNeedle(
  addressed: () => string,
  route: ReturnType<typeof useRoute>,
  router: ReturnType<typeof useRouter>,
): Ref<string> {
  const needle = ref(addressed())
  watch(addressed, (text) => {
    if (text !== needle.value) needle.value = text
  })
  watch(needle, (text) => {
    if (text === addressed()) return
    const next = { ...route.query }
    if (text) next.q = text
    else delete next.q
    // A new search starts at the first page (CF-1191).
    delete next.page
    void router.replace({ query: next })
  })
  return needle
}

/** The filter box's text and the list's page size, which outlive a filter and a sort; the page
 *  does not (CF-1191). */
function searchedOf(needle: string, size: string): Pairs {
  return [...(needle ? [['q', needle]] : []), ...(size ? [['size', size]] : [])] as Pairs
}

export function useTicketQuery(): TicketQuery {
  const route = useRoute()
  const router = useRouter()

  const pairs = computed<Pairs>(() =>
    Object.entries(route.query).flatMap(([key, value]) =>
      (Array.isArray(value) ? value : [value])
        .filter((v): v is string => typeof v === 'string')
        .map((v): [string, string] => [key, v]),
    ),
  )
  const query = computed(() => filterPairs(pairs.value))
  const setting = (key: string) => pairs.value.find(([k]) => k === key)?.[1] ?? ''
  const lanes = computed<Lanes>(() =>
    ['repository', 'assignee'].includes(setting('lanes')) ? (setting('lanes') as Lanes) : '',
  )
  const sort = computed(() =>
    (SORTS as readonly string[]).includes(setting('sort')) ? setting('sort') : '',
  )
  const direction = computed(() => setting('dir'))
  const order = computed<Pairs>(() =>
    sort.value
      ? [
          ['sort', sort.value],
          ['dir', direction.value],
        ]
      : [],
  )
  const grouping = computed<Pairs>(() => (lanes.value ? [['lanes', lanes.value]] : []))
  const needle = useNeedle(() => setting('q'), route, router)
  const searched = computed(() => searchedOf(needle.value, setting('size')))
  const kept = computed<Pairs>(() => [...order.value, ...grouping.value, ...searched.value])

  const toggleUrl = (key: string, value: string) =>
    urlOf(route.path, [...toggled(query.value, key, value), ...kept.value])
  const clearUrl = computed(() => urlOf(route.path, kept.value))
  const boardUrl = computed(() =>
    urlOf('/tickets', [...query.value, ...grouping.value, ...searched.value]),
  )
  const listUrl = computed(() =>
    urlOf('/tickets/list', [...query.value, ...grouping.value, ...searched.value]),
  )
  const lanesUrl = (value: string) =>
    urlOf(route.path, [
      ...query.value,
      ...order.value,
      ...(value ? ([['lanes', value]] as Pairs) : []),
      ...searched.value,
    ])
  const sortUrl = (column: Sort) =>
    urlOf('/tickets/list', [
      ...query.value,
      ['sort', column],
      ['dir', sort.value === column && direction.value !== 'desc' ? 'desc' : 'asc'],
      ...grouping.value,
      ...searched.value,
    ])
  const chips = computed(() =>
    query.value.map(([key, value]) => ({
      key,
      value,
      href: urlOf(route.path, [
        ...query.value.filter(([k, v]) => !(k === key && v === value)),
        ...kept.value,
      ]),
    })),
  )

  return {
    query,
    lanes,
    sort,
    direction,
    needle,
    chips,
    clearUrl,
    boardUrl,
    listUrl,
    toggleUrl,
    lanesUrl,
    sortUrl,
  }
}
