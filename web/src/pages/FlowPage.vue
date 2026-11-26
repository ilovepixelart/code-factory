<script setup lang="ts">
import SectionCard from '../components/SectionCard.vue'
import { Analytics01Icon, Tick02Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import AnalyticsFrame from '../components/AnalyticsFrame.vue'
import { FLOW, rangeOf } from '../lib/analytics'
import { computed, nextTick, shallowRef, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import DataTable from '../components/data-table/DataTable.vue'
import type { DataTableColumn } from '../components/data-table/features'
import FlowTiles from '../components/flow/FlowTiles.vue'
import GateTimings from '../components/flow/GateTimings.vue'
import QuestionWait from '../components/flow/QuestionWait.vue'
import OutcomeTiles from '../components/flow/OutcomeTiles.vue'
import HeldTiles from '../components/flow/HeldTiles.vue'
import MergedTable from '../components/flow/MergedTable.vue'
import PullsChart from '../components/flow/PullsChart.vue'
import { ask } from '../lib/actions'
import { STAGE_LABELS } from '../lib/board'
import { chartPoints, type Dashboard } from '../lib/factory'
import { useFactoryRead } from '../lib/factoryRead'
import { span } from '../lib/format'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { readAgain } from '../lib/queries'
import { keys } from '../lib/queryKeys'
import type { Flow } from '../lib/metrics'
import { refusalText } from '../lib/notice'
import { HELD, heldList, notHeld } from '../lib/shipped'
import TicketHoverCard from '../components/TicketHoverCard.vue'
import { NUMBER } from '../components/data-table/look'

// What shipped and what is stuck (CF-1203), from git and the board's records: the pull requests
// merged in the range with how long each branch's work took, the tickets on a branch past the
// usual lead time. What the work cost and its runs are the Factory page's. Beside what shipped, whether it held (CF-1215):
// the merges reverted later, those a later ticket names as its cause, and those merged without the
// board's checks having passed on their head, each figure a link that lists its merges.
const TABLE_SIZE = 10

const route = useRoute()
const range = computed(() => rangeOf(route.query.range))
// Each range is its own read (`keys.flow`); a failed one leaves the last answer shown, beside why.
const client = useQueryClient()
const flowKey = computed(() => keys.flow(range.value))
const flowRead = useQuery({
  queryKey: flowKey,
  queryFn: ({ signal }) => ask<Flow>(`/api/flow?range=${range.value}`, signal),
})
const flow = shallowRef<Flow | null>(null)
watch(
  flowRead.data,
  (answer) => {
    if (answer) flow.value = answer
  },
  { immediate: true },
)
const failed = computed(() => (flowRead.error.value ? refusalText(flowRead.error.value) : ''))
const refresh = () => readAgain(client, flowKey.value, flowRead)

const merged = computed(() => flow.value?.merged ?? [])
// The chart's opened and merged pull requests per bucket are the factory series of the range.
const series = useFactoryRead<Dashboard>(
  ({ from, to }) => `/api/factory/dashboard?from=${from}&to=${to}`,
)
const points = computed(() => (series.data.value ? chartPoints(series.data.value.series) : []))
function retry(): void {
  void refresh()
  void series.refresh()
}
// The merges the address asks for: all of them, or those that did not hold in one way.
const filter = computed(() => HELD.find((h) => h.key === route.query.held) ?? null)
const listed = computed(() => {
  const kind = filter.value?.key
  return kind ? merged.value.filter((m) => notHeld(m, kind)) : merged.value
})
// A figure's link changes only the list far below it: bring the list to the figure's reader.
watch(
  () => filter.value?.key,
  async (kind) => {
    if (!kind) return
    await nextTick()
    document.getElementById('merged-heading')?.scrollIntoView({ block: 'start' })
  },
)
// "newest first" holds only while no column sort is chosen in the address.
const mergedNote = computed(() => {
  const order = route.query.merged_sort ? '' : 'newest first'
  if (filter.value) return [filter.value.hint, order].filter(Boolean).join(', ')
  const lead = 'lead is from filing the ticket to the merge'
  return order ? `${order}; ${lead}` : lead
})
type Stuck = Flow['stuck'][number]
const STUCK_COLUMNS: DataTableColumn<Stuck>[] = [
  {
    id: 'ticket',
    accessorFn: (t) => `${t.id} ${t.title}`,
    header: 'Ticket',
    meta: { cell: 'min-w-56 whitespace-normal' },
  },
  {
    id: 'stage',
    accessorFn: (t) => STAGE_LABELS[t.stage],
    header: 'Stage',
    meta: { cell: 'whitespace-nowrap' },
  },
  { id: 'age', accessorFn: (t) => t.age ?? -1, header: 'On its branch', meta: NUMBER },
  {
    id: 'needs',
    header: 'Needs',
    enableSorting: false,
    meta: { cell: 'whitespace-normal text-muted-foreground' },
  },
]
// Needs is a column only while a stuck ticket records one: a column of blanks is noise.
const stuckColumns = computed(() =>
  flow.value?.stuck.some((t) => t.needs)
    ? STUCK_COLUMNS
    : STUCK_COLUMNS.filter((c) => c.id !== 'needs'),
)
const multiRepository = computed(() => new Set(merged.value.map((m) => m.repository)).size > 1)
// Every stuck ticket is past the threshold, so the error tone marks only those past twice it.
const overdue = (age: number | null): boolean =>
  age !== null && flow.value !== null && age > 2 * flow.value.stuck_after
// A section's count while its table's filter narrows it: what the filter keeps of all.
const stuckShown = shallowRef<number | null>(null)
const mergedShown = shallowRef<number | null>(null)
const counted = (shown: number | null, all: number): number | string =>
  shown !== null && shown < all ? `${String(shown)} of ${String(all)}` : all
</script>

<template>
  <AnalyticsFrame
    :page="FLOW"
    what="the flow"
    ranged
    :ready="flow !== null"
    :failed="failed"
    :shown="flow?.range ?? null"
    @retry="retry()"
  >
    <template v-if="flow">
      <OutcomeTiles :flow="flow" />

      <HeldTiles :merged="merged" />

      <FlowTiles :flow="flow" />

      <QuestionWait :range="range" />

      <GateTimings />

      <PullsChart
        v-if="series.data.value"
        :points="points"
        :weekly="series.data.value.series.bucket === 'week'"
      />

      <SectionCard
        heading="stuck-heading"
        title="Stuck"
        :count="counted(stuckShown, flow.stuck.length)"
        :description="`On a branch longer than ${span(flow.stuck_after)}: the time 85% of merged tickets took, or a day until 5 merges set it`"
        :empty="!flow.stuck.length"
      >
        <template #empty
          ><Empty
            ><EmptyHeader
              ><EmptyMedia variant="icon"
                ><HugeiconsIcon :icon="Tick02Icon" aria-hidden="true" /></EmptyMedia
              ><EmptyTitle>{{
                `Nothing on a branch longer than ${span(flow.stuck_after)}`
              }}</EmptyTitle
              ><EmptyDescription
                >Tickets appear here when they pass the branch age threshold.</EmptyDescription
              ></EmptyHeader
            ></Empty
          ></template
        >
        <DataTable
          v-if="flow.stuck.length"
          :columns="stuckColumns"
          :data="flow.stuck"
          :row-id="(t: Stuck) => `${t.repository}/${t.id}`"
          caption="Stuck"
          prefix="stuck_"
          :paged="{ label: 'stuck tickets', fallback: TABLE_SIZE }"
          :filter="{
            column: 'ticket',
            label: 'Filter stuck tickets',
            placeholder: 'Filter by ticket or title',
            none: 'stuck ticket',
          }"
          @shown="stuckShown = $event"
        >
          <template #cell-ticket="{ row: t }">
            <TicketHoverCard :repository="t.repository" :ticket="t.id" class="hover:underline"
              ><span class="font-mono text-muted-foreground">{{ t.id }}&nbsp;</span
              ><span class="font-medium">{{ t.title }}</span></TicketHoverCard
            >
          </template>
          <template #cell-age="{ row: t }"
            ><span :class="overdue(t.age) ? 'text-destructive' : 'text-muted-foreground'">{{
              t.age === null ? 'unknown' : span(t.age)
            }}</span></template
          >
          <template #cell-needs="{ row: t }">{{ t.needs }}</template>
        </DataTable>
      </SectionCard>

      <SectionCard
        heading="merged-heading"
        title="Recently merged"
        :count="counted(mergedShown, listed.length)"
        :description="mergedNote"
        :empty="!listed.length"
      >
        <template #empty
          ><Empty
            ><EmptyHeader
              ><EmptyMedia variant="icon"
                ><HugeiconsIcon
                  :icon="filter ? Tick02Icon : Analytics01Icon"
                  aria-hidden="true" /></EmptyMedia
              ><EmptyTitle>{{ filter ? filter.none : 'Nothing merged in this range' }}</EmptyTitle
              ><EmptyDescription>{{
                filter
                  ? 'Open the full list to see merges outside this filter.'
                  : 'Try a wider date range to see earlier merges.'
              }}</EmptyDescription></EmptyHeader
            ></Empty
          ></template
        >
        <template #action
          ><RouterLink
            v-if="filter"
            :to="heldList(route.query, null)"
            class="underline-offset-4 hover:underline text-sm"
            >all {{ merged.length }} merged</RouterLink
          ></template
        >

        <MergedTable
          v-if="listed.length"
          :rows="listed"
          :now="flow.now"
          :multi-repository="multiRepository"
          :size="TABLE_SIZE"
          @shown="mergedShown = $event"
        />
      </SectionCard>
    </template>
  </AnalyticsFrame>
</template>
