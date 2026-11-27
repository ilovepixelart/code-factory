<script setup lang="ts">
import { computed } from 'vue'
import { thousands } from '../lib/format'
import { loadGroups, sizeOf, type MemoryRecord } from '../lib/memory'
import { Progress } from '@/components/ui/progress'

// What a session loads, against the budget recall uses, and its bar. Once it nears the budget
// (`NEAR` of it) or an entry is left out, also what each role's runs and path entries add, what the
// budget leaves out, and how many load nowhere (CF-1171-R2, CF-1195). Flat on the inset panel like a
// section (SectionCard's heading row), one meter so its value is read whole; its slot is the row's action.
const {
  active,
  loaded,
  ceiling,
  rulesOver = 0,
} = defineProps<{
  active: MemoryRecord[]
  loaded: number
  ceiling: number
  rulesOver?: number
}>()
defineSlots<{ default?: () => unknown }>()
const NEAR = 0.8
const groups = computed(() => Object.fromEntries(loadGroups(active)))
const adds = computed(() =>
  (
    [
      ['spec', 'Spec runs add'],
      ['build', 'Build runs add'],
      ['review', 'Review runs add'],
      ['paths', 'Sessions changing a path add up to'],
    ] as const
  )
    .map(([group, words]) => [words, sizeOf(groups.value[group] ?? [])] as const)
    .filter(([, size]) => size > 0)
    .map(([words, size]) => `${words} ${thousands(size)}.`),
)
const left = computed(() => active.filter((r) => r.left_out))
const off = computed(() => groups.value.off?.length ?? 0)
const over = computed(() => loaded > ceiling)
const near = computed(() => loaded >= ceiling * NEAR || left.value.length > 0 || rulesOver > 0)
</script>

<template>
  <div data-memory-meter data-section class="flex min-w-0 flex-col gap-3 rounded-lg bg-muted p-4">
    <div class="flex min-h-7 items-center gap-3">
      <p class="cn-font-heading min-w-0 flex-1 text-sm font-medium">
        Every session loads <b>{{ thousands(loaded) }}</b> of {{ thousands(ceiling) }} characters
      </p>
      <div v-if="$slots.default" class="shrink-0"><slot /></div>
    </div>
    <div class="grid gap-1.5 text-sm">
      <meter
        class="sr-only"
        aria-label="Loaded into every agent session"
        min="0"
        :value="loaded"
        :max="ceiling"
      />
      <!-- The meter beside it carries the value; the bar only draws it. -->
      <Progress
        class="bg-border"
        :model-value="Math.min(100, (loaded / ceiling) * 100)"
        aria-hidden="true"
      />
      <template v-if="near">
        <span v-if="over" class="text-sm text-destructive"
          >Above the ceiling: retire or merge entries.</span
        >
        <span v-if="rulesOver > 0" class="text-sm text-destructive"
          >Rules and decisions take {{ thousands(rulesOver) }} characters over the budget: merge,
          scope or retire one.</span
        >
        <span v-if="left.length" class="grid gap-0.5 text-sm"
          ><span class="text-destructive">Left out over the budget:</span
          ><a
            v-for="r in left"
            :key="`${r.repository}/${r.id}`"
            :href="`#${r.id}`"
            class="justify-self-start wrap-anywhere hover:underline"
            >{{ r.statement }}</a
          ></span
        >
        <span v-else class="text-muted-foreground text-sm">Nothing is left out.</span>
        <span class="text-muted-foreground text-sm"
          >{{ adds.join(' ') }}{{ adds.length ? ' ' : '' }}Not loaded: {{ off }}
          {{ off === 1 ? 'entry' : 'entries' }}.</span
        >
      </template>
    </div>
  </div>
</template>
