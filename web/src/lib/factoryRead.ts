// The Factory pages' read: one answer of the range the address names, read again when the range
// changes. Only the latest read applies; an answer keeps what was shown until the next one comes,
// and a read that fails says why beside the figures it left. Each range is its own query
// (`keys.factory`), so a range read before shows at once when it is picked again.

import { keepPreviousData, useQuery } from '@tanstack/vue-query'
import { computed, shallowRef, watch, type ComputedRef, type Ref } from 'vue'
import { useRoute } from 'vue-router'
import { ask } from './actions'
import { bounds, rangeOf, type RangeKey } from './factory'
import { refusalText } from './notice'
import { keys } from './queryKeys'

export interface FactoryRead<T> {
  range: ComputedRef<RangeKey>
  data: Readonly<Ref<T | null>>
  /** The reason the latest read failed; empty once one answers. */
  failed: Readonly<Ref<string>>
  /** The range the answer in `data` was read for. */
  shown: Readonly<Ref<RangeKey | null>>
  /** Whether a read is under way. */
  busy: Readonly<Ref<boolean>>
  refresh: () => Promise<void>
}

/** Read a Factory endpoint for the selected range. Each request captures its own timestamp. */
export function useFactoryRead<T>(path: string, ranged = true): FactoryRead<T> {
  const route = useRoute()
  const range = computed(() => rangeOf(route.query.range))
  const query = useQuery({
    queryKey: computed(() => keys.factory(path, ranged ? range.value : null)),
    queryFn: async ({ queryKey: [, endpoint, asked], signal }) => {
      const dateRange = asked === null ? null : bounds(asked, new Date())
      const url = dateRange ? `${endpoint}?from=${dateRange.from}&to=${dateRange.to}` : endpoint
      return { asked, answer: await ask<T>(url, signal) }
    },
    placeholderData: keepPreviousData,
  })
  // The last answer of any range: Query drops a placeholder once the new range's read fails.
  const last = shallowRef<{ asked: RangeKey | null; answer: T } | null>(null)
  watch(
    query.data,
    (answered) => {
      if (answered) last.value = answered
    },
    { immediate: true },
  )
  return {
    range,
    data: computed(() => last.value?.answer ?? null),
    shown: computed(() => last.value?.asked ?? null),
    failed: computed(() =>
      query.error.value && !query.isFetching.value ? refusalText(query.error.value) : '',
    ),
    busy: query.isFetching,
    refresh: async () => {
      await query.refetch()
    },
  }
}
