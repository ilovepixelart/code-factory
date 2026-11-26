<script setup lang="ts">
import StatusBadge from './StatusBadge.vue'
import { Badge } from '@/components/ui/badge'
import { computed, inject } from 'vue'
import { day } from '../lib/format'
import { entryPath, itemActions } from '../lib/itemActions'
import { BOARD } from '../lib/live'
import { dateOf, type MemoryPair, type MemoryRecord } from '../lib/memory'
import MemoryQueue from './MemoryQueue.vue'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { FieldError } from '@/components/ui/field'

// Pairs of entries on one subject that consolidate flags (CF-1165), the older beside the newer;
// Newer supersedes older retires the older through the newer entry's `supersedes`
// (CF-1171-R1).
const { pairs, active } = defineProps<{ pairs: MemoryPair[]; active: MemoryRecord[] }>()
const emit = defineEmits<{ changed: [] }>()
const { busy, errors, run } = itemActions(() => {
  emit('changed')
})
const live = inject(BOARD, undefined)
const today = computed(() => live?.board.value?.today ?? dateOf(Date.now() / 1000))
const keyOf = (p: MemoryPair): string => `${p.repository}/${p.one}/${p.other}`

interface Side {
  id: string
  statement: string
  date: string
}

/** The pair's two entries, the older first by date, then by id. */
const sides = computed(() =>
  Object.fromEntries(
    pairs.map((p) => {
      const side = (id: string, statement: string): Side => ({
        id,
        statement,
        date: active.find((r) => r.repository === p.repository && r.id === id)?.date ?? '',
      })
      const both = [side(p.one, p.one_statement), side(p.other, p.other_statement)].sort(
        (a, b) => a.date.localeCompare(b.date) || a.id.localeCompare(b.id),
      )
      return [keyOf(p), both]
    }),
  ),
)

function supersede(p: MemoryPair): Promise<void> {
  const [older, newer] = sides.value[keyOf(p)] ?? []
  return run(keyOf(p), 'PATCH', entryPath(p.repository, newer?.id ?? ''), {
    supersedes: older?.id ?? '',
  })
}
</script>

<template>
  <MemoryQueue
    id="memory-flags"
    title="Flagged by consolidate"
    hint="two entries on one subject"
    :rows="pairs"
    :key-of="keyOf"
  >
    <template #row="{ row: p }">
      <article
        :aria-label="`${p.one_statement} and ${p.other_statement}`"
        class="grid gap-2 px-4 py-3 text-sm"
      >
        <span class="text-muted-foreground flex flex-wrap items-center gap-x-2 gap-y-1 text-sm"
          ><StatusBadge v-if="p.contradicts" key="badge-1" tone="warning">Contradicts</StatusBadge
          ><Badge v-else key="badge-2" variant="outline">same subject</Badge
          ><span>both say {{ p.terms.join(', ') }}</span></span
        >
        <div class="grid gap-2 md:grid-cols-2">
          <div v-for="(side, n) in sides[keyOf(p)]" :key="side.id" class="grid gap-0.5">
            <span class="text-muted-foreground text-sm" :title="side.date"
              >{{ n === 0 ? 'older' : 'newer' }}, {{ day(side.date, side.date, today) }}</span
            >
            <span class="wrap-anywhere">{{ side.statement }}</span>
          </div>
        </div>
        <div class="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="secondary"
            :disabled="busy.has(keyOf(p))"
            @click="supersede(p)"
          >
            <Spinner v-if="busy.has(keyOf(p))" data-icon="inline-start" />Newer supersedes older
          </Button>
        </div>
        <FieldError v-if="errors[keyOf(p)]">{{ errors[keyOf(p)] }}</FieldError>
      </article>
    </template>
  </MemoryQueue>
</template>
