<script setup lang="ts">
import StatusBadge from '../StatusBadge.vue'
import { computed } from 'vue'
import { ESTIMATE_NOTE, thousands, cost } from '../../lib/format'
import type { Expensive } from '../../lib/factory'
import { ticketHref } from '../../lib/ticket'
import DataTable from '../data-table/DataTable.vue'
import type { DataTableColumn } from '../data-table/features'
import { AMOUNT } from '../data-table/look'
import { Badge } from '@/components/ui/badge'

// The dearest pull requests of the range: the number linked to GitHub with its title (and its
// repository when the list spans more than one), its ticket, size, runs, cost and state. A cost
// missing a run of the ticket says it is partial. The rows sort in the address under `pulls_`.
const { rows } = defineProps<{ rows: Expensive[] }>()

const multiRepository = computed(() => new Set(rows.map((r) => r.repository)).size > 1)
const lines = (pull: Expensive): string =>
  pull.changed_lines === null
    ? 'lines not recorded'
    : `${thousands(pull.changed_lines)} changed lines`
const NOWRAP = 'whitespace-nowrap'
const COLUMNS: DataTableColumn<Expensive>[] = [
  {
    id: 'pr',
    accessorFn: (p) => p.number,
    header: 'Pull request',
    meta: { cell: 'whitespace-normal wrap-anywhere md:min-w-56' },
  },
  { id: 'ticket', accessorFn: (p) => p.ticket ?? '', header: 'Ticket', meta: { cell: NOWRAP } },
  { accessorKey: 'size', header: 'Size', meta: { cell: NOWRAP } },
  { accessorKey: 'runs', header: 'Runs', meta: AMOUNT },
  {
    accessorKey: 'cost',
    header: 'Cost',
    meta: {
      cell: `${NOWRAP} ${AMOUNT.cell}`,
      head: AMOUNT.head,
      title: (p: Expensive) => (p.estimated ? ESTIMATE_NOTE : undefined),
    },
  },
  { accessorKey: 'state', header: 'State', meta: { cell: NOWRAP } },
]
</script>

<template>
  <DataTable
    :columns="COLUMNS"
    :data="rows"
    :row-id="(p: Expensive) => p.url"
    caption="Most expensive pull requests"
    prefix="pulls_"
    stacked="labelled"
  >
    <template #cell-pr="{ row: pull }">
      <a
        :href="pull.url"
        class="underline-offset-4 hover:underline tabular-nums"
        target="_blank"
        rel="noopener noreferrer"
        >#{{ pull.number }}</a
      >&nbsp;<span class="font-medium">{{ pull.title }}</span
      ><span v-if="multiRepository" class="text-muted-foreground">&nbsp;{{ pull.repository }}</span>
    </template>
    <template #cell-ticket="{ row: pull }">
      <RouterLink
        v-if="pull.ticket"
        :to="ticketHref(pull.repository, pull.ticket)"
        class="font-mono hover:underline"
        >{{ pull.ticket }}</RouterLink
      >
      <span v-else class="text-muted-foreground">none</span>
    </template>
    <template #cell-size="{ row: pull }">
      <Badge variant="outline" :title="lines(pull)">{{ pull.size }}</Badge>
    </template>
    <template #cell-cost="{ row: pull }">
      {{ cost(pull.cost, pull.estimated)
      }}<template v-if="!pull.cost_complete"
        >&nbsp;<StatusBadge tone="warning">Partial</StatusBadge></template
      >
    </template>
    <template #cell-state="{ row: pull }">
      <StatusBadge :state="pull.state" />
    </template>
  </DataTable>
</template>
