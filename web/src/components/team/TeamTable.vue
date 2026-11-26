<script setup lang="ts">
import { age, alsoLine, pullDot, pullWords, rowLine, type TeamRow } from '../../lib/teamNow'
import TeamActor from './TeamActor.vue'
import { Button } from '@/components/ui/button'
import DataTable from '../data-table/DataTable.vue'
import type { DataTableColumn } from '../data-table/features'
import StatusBadge from '../StatusBadge.vue'
import TicketHoverCard from '../TicketHoverCard.vue'

const { rows, caption, now, selected } = defineProps<{
  rows: TeamRow[]
  caption: string
  now: number
  selected: string
}>()
const emit = defineEmits<{ select: [key: string] }>()

// Team orders each group by its state and age. Mobile cards keep the same controls and order.
const columns: DataTableColumn<TeamRow>[] = [
  {
    id: 'status',
    header: 'Status',
    enableSorting: false,
    meta: { head: '@3xl:w-[16%]', cell: 'max-md:order-1' },
  },
  {
    id: 'ticket',
    header: 'Ticket',
    enableSorting: false,
    meta: { head: '@3xl:w-[8%]', cell: 'max-md:order-2' },
  },
  {
    id: 'title',
    header: 'Title',
    enableSorting: false,
    meta: { cell: 'whitespace-normal wrap-anywhere max-md:order-4 max-md:basis-full' },
  },
  {
    id: 'actor',
    header: 'Actor',
    enableSorting: false,
    meta: { head: '@3xl:w-[12%]', cell: 'whitespace-normal wrap-anywhere max-md:order-5' },
  },
  {
    id: 'activity',
    header: 'Activity',
    enableSorting: false,
    meta: { head: '@3xl:w-[19%]', cell: 'whitespace-normal wrap-anywhere max-md:order-6' },
  },
  {
    id: 'pull',
    header: 'Pull request',
    enableSorting: false,
    meta: {
      head: '@3xl:w-[15%]',
      cell: 'whitespace-normal wrap-anywhere max-md:order-7 max-md:basis-full max-md:empty:hidden',
    },
  },
  {
    id: 'age',
    header: 'Age',
    enableSorting: false,
    meta: {
      head: 'text-right @3xl:w-[6%]',
      cell: 'text-right tabular-nums max-md:order-3 max-md:ml-auto',
    },
  },
]
const rowId = (row: TeamRow) => row.key
const rowAttrs = (row: TeamRow) => ({
  'data-row': row.key,
  'data-team-selected': String(row.key === selected),
})
const title = (row: TeamRow) => (row.ticket ? row.ticket.title || 'Ticket details' : row.actor.name)
</script>

<template>
  <DataTable
    :columns="columns"
    :data="rows"
    :caption="caption"
    :row-id="rowId"
    :row-attrs="rowAttrs"
    class="@container"
    table-class="@3xl:table-fixed"
    row-class="data-[team-selected=true]:bg-muted"
    stacked
  >
    <template #cell-status="{ row }">
      <StatusBadge :state="row.state" :quiet="row.state !== 'owner' && row.state !== 'stale'" />
    </template>
    <template #cell-ticket="{ row }">
      <TicketHoverCard
        v-if="row.ticket"
        :repository="row.ticket.repository"
        :ticket="row.ticket.id"
        class="font-mono underline-offset-4 hover:underline"
        >{{ row.ticket.id }}</TicketHoverCard
      >
    </template>
    <template #cell-title="{ row }">
      <Button
        type="button"
        variant="ghost"
        class="h-auto min-h-6 max-w-full justify-start whitespace-normal px-0 text-left underline-offset-4 hover:underline"
        :aria-pressed="row.key === selected"
        :aria-label="row.ticket && !row.ticket.title ? `Details for ${row.ticket.id}` : undefined"
        @click="emit('select', row.key)"
      >
        {{ title(row) }}
      </Button>
    </template>
    <template #cell-actor="{ row }">
      <TeamActor :kind="row.actor.kind" :name="row.actor.name" />
    </template>
    <template #cell-activity="{ row }">
      <span class="grid text-muted-foreground">
        <span>{{ rowLine(row) }}</span>
        <span v-for="other in row.also" :key="`${other.state}-${other.actor.name}`" data-also>
          {{ alsoLine(other, now) }}
        </span>
      </span>
    </template>
    <template #cell-pull="{ row }">
      <span v-if="row.pull" class="flex items-center gap-1.5">
        <span
          class="size-1.5 shrink-0 rounded-full"
          :class="pullDot(row.pull)"
          aria-hidden="true"
        ></span>
        <a :href="row.pull.url" class="font-mono underline-offset-4 hover:underline"
          >#{{ row.pull.number }}</a
        >
        <span class="text-muted-foreground">{{ pullWords(row.pull) }}</span>
      </span>
    </template>
    <template #cell-age="{ row }"
      ><span class="text-muted-foreground">{{ age(row, now) }}</span></template
    >
  </DataTable>
</template>
