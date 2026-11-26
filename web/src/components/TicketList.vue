<script setup lang="ts">
import { sentence } from '../lib/format'
import { Badge } from '@/components/ui/badge'
import { computed } from 'vue'
import { STAGE_LABELS, type Card } from '../lib/board'
import { useLabelColor } from '../lib/labels'
import { chosen, keyOf } from '../lib/selection'
import type { Sort } from '../lib/view'
import { ticketHref } from '../lib/ticket'
import ColorDot from './ColorDot.vue'
import CutText from './CutText.vue'
import DataTable from './data-table/DataTable.vue'
import type { DataTableColumn } from './data-table/features'
import DeliveryStatus from './DeliveryStatus.vue'
import StageGlyph from './StageGlyph.vue'

// The list view: the page of cards the Tickets page sorted and paged, each row ticked into the
// bulk selection the board's cards share.
const { rows, sort, direction, sortUrl } = defineProps<{
  rows: Card[]
  sort: string
  direction: string
  sortUrl: (column: Sort) => string
}>()

const MUTED = { cell: 'text-muted-foreground' }
const COLUMNS: DataTableColumn<Card>[] = [
  {
    accessorKey: 'id',
    header: 'ID',
    enableHiding: false,
    meta: { cell: 'font-mono text-muted-foreground' },
  },
  {
    accessorKey: 'title',
    header: 'Title',
    enableHiding: false,
    meta: { cell: 'min-w-48 font-medium whitespace-normal wrap-anywhere max-md:basis-full' },
  },
  {
    accessorKey: 'type',
    header: 'Type',
    cell: ({ getValue }) => sentence(String(getValue() ?? '')),
    meta: MUTED,
  },
  { accessorKey: 'stage', header: 'Stage', meta: MUTED },
  {
    accessorKey: 'priority',
    header: 'Priority',
    cell: ({ getValue }) => sentence(String(getValue() ?? '')),
    meta: MUTED,
  },
  { id: 'labels', header: 'Labels', enableSorting: false },
  { accessorKey: 'assignee', header: 'Assignee', meta: MUTED },
  { accessorKey: 'repository', header: 'Repository', meta: MUTED },
]
const labelColor = useLabelColor()
// A column every shown row leaves empty, or fills with one value, tells nothing (CF-1079).
const columns = computed(() =>
  COLUMNS.filter((c) => {
    const key = 'accessorKey' in c ? c.accessorKey : c.id
    if (key === 'assignee') return rows.some((r) => r.assignee !== '')
    if (key === 'repository') return new Set(rows.map((r) => r.repository)).size > 1
    return true
  }),
)
const rowId = (card: Card): string => keyOf(card.repository, card.id)
</script>

<template>
  <!-- The rows scroll under a header that stays: the table's own scroller takes the height the
       caller gives its frame. -->
  <div class="flex min-h-0 flex-col">
    <DataTable
      class="min-h-0 flex-1"
      frame-class="flex min-h-0 flex-1 flex-col overflow-hidden *:data-[slot=table-container]:min-h-0 *:data-[slot=table-container]:flex-1 *:data-[slot=table-container]:overflow-auto"
      :columns="columns"
      :data="rows"
      :row-id="rowId"
      caption="Tickets"
      :row-label="(card: Card) => `${card.id} ${card.title}`"
      :selected="chosen"
      :manual="{ sort: [sort, direction], sortHref: (key: string) => sortUrl(key as Sort) }"
      :row-attrs="(card: Card) => ({ 'data-ticket': card.id, 'data-repository': card.repository })"
      hideable
      columns-key="codeFactoryListColumns"
      stacked
      header-class="sticky top-0 z-10"
    >
      <template #cell-title="{ row: card }">
        <RouterLink :to="ticketHref(card.repository, card.id)" class="hover:underline">{{
          card.title
        }}</RouterLink>
      </template>
      <template #cell-stage="{ row: card }">
        <span class="flex items-center gap-1.5 whitespace-nowrap" data-stage-cell
          ><StageGlyph :stage="card.stage" decorative />{{ STAGE_LABELS[card.stage]
          }}<DeliveryStatus :card="card"
        /></span>
      </template>
      <template #cell-labels="{ row: card }">
        <div class="flex flex-wrap gap-1">
          <Badge v-for="label in card.labels" :key="label" variant="outline"
            ><ColorDot :color="labelColor(label)" /><CutText :text="label"
          /></Badge>
        </div>
      </template>
      <template #cell-priority="{ row: card }">{{ card.priority || 'none' }}</template>
      <template #cell-assignee="{ row: card }"><CutText :text="card.assignee" /></template>
      <template #cell-repository="{ row: card }"><CutText :text="card.repository" /></template>
    </DataTable>
  </div>
</template>
