<script setup lang="ts">
import { computed } from 'vue'
import { count, span } from '../../lib/format'
import type { Flow } from '../../lib/metrics'
import { perDay } from '../../lib/shipped'
import TileFigure from '../TileFigure.vue'
import { Card, CardDescription, CardFooter, CardHeader } from '@/components/ui/card'
import { cn } from '@/lib/utils'

// Flow's throughput, after its outcomes (OutcomeTiles) and what held (HeldTiles), as dashboard-01's
// section cards: what shipped, how long it took, the median time per column and what is in flight. Each card
// is a group named for its figure; a figure with nothing to show is `null`, drawn as a placeholder.
const { flow } = defineProps<{ flow: Flow }>()

const COLUMNS = [
  ['spec', 'Spec'],
  ['build', 'Build'],
  ['review', 'Review'],
] as const

const withTicket = computed(() => flow.merged.filter((m) => m.ticket !== null).length)
const daily = computed(() => perDay(flow.merged.length, flow.since, flow.now))
const tiles = computed(() => [
  {
    name: 'Shipped',
    value: count(flow.merged.length),
    note: `${String(daily.value)} a day · ${String(withTicket.value)} with a ticket`,
  },
  {
    name: 'Lead time',
    value: flow.lead.median === null ? null : span(flow.lead.median),
    note: leadNote(),
  },
  ...COLUMNS.map(([key, label]) => ({
    name: `${label} time`,
    value: minutes(flow.columns[key]),
    note: 'median per merged ticket',
  })),
])

// Column times are whole minutes from the board's clock: under one is not zero time.
function minutes(value: number | null): string | null {
  if (value === null) return null
  return value < 1 ? 'under 1m' : span(value * 60)
}

function leadNote(): string {
  const { p85, count: measured } = flow.lead
  const p95 = flow.lead.p95 ?? null
  if (p95 !== null) return `95% within ${span(p95)} · ${String(measured)} measured`
  // The figures time from a ticket's filing only; a merge without one is timed from its first commit.
  const fromCommit = flow.merged.filter((m) => m.from === 'first_commit').length
  if (p85 === null && fromCommit)
    return `no filed ticket to time from; ${String(fromCommit)} timed from a first commit`
  if (p85 === null) return 'no measured lead times'
  return `median from filing to merge; 85% within ${span(p85)}`
}
</script>

<template>
  <section
    aria-label="At a glance"
    class="grid grid-cols-1 gap-3 min-[360px]:grid-cols-2 md:grid-cols-3"
  >
    <Card
      v-for="t in tiles"
      :key="t.name"
      class="@container/card"
      size="sm"
      role="group"
      :aria-label="t.name"
    >
      <CardHeader>
        <CardDescription>{{ t.name }}</CardDescription>
        <TileFigure :value="t.value" />
      </CardHeader>
      <CardFooter class="text-muted-foreground">
        <p>{{ t.note }}</p>
      </CardFooter>
    </Card>
    <Card class="@container/card" size="sm" role="group" aria-label="In flight">
      <CardHeader>
        <CardDescription>In flight</CardDescription>
        <TileFigure :value="String(flow.in_flight)" />
      </CardHeader>
      <CardFooter :class="cn(flow.stuck.length ? 'text-destructive' : 'text-muted-foreground')">
        <p>
          {{ flow.stuck.length ? flow.stuck.length : 'none' }} on a branch over
          {{ span(flow.stuck_after) }}
        </p>
      </CardFooter>
    </Card>
  </section>
</template>
