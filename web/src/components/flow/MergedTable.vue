<script setup lang="ts">
import { computed } from 'vue'
import { span } from '../../lib/format'
import type { Merged } from '../../lib/metrics'
import TicketHoverCard from '../TicketHoverCard.vue'
import DataTable from '../data-table/DataTable.vue'
import type { DataTableColumn } from '../data-table/features'
import { NUMBER } from '../data-table/look'

// The merged pull requests of Recently merged (CF-1203), each with how it held (CF-1215):
// reverted, the tickets naming its ticket as their cause, and what the board's checks said of its
// head. Sorted, filtered and paged in the address under `merged_`.
const { rows, now, multiRepository, size } = defineProps<{
  rows: Merged[]
  now: number
  multiRepository: boolean
  size: number
}>()
defineEmits<{
  /** How many merges the table's filter keeps, for the section's count. */
  shown: [count: number]
}>()

const NOWRAP = 'whitespace-nowrap tabular-nums'
const columns = computed<DataTableColumn<Merged>[]>(() => [
  {
    id: 'work',
    accessorFn: (m) => (m.ticket ? `${m.ticket} ${m.title || m.branch}` : m.branch),
    header: 'Ticket',
    enableHiding: false,
    meta: { cell: 'whitespace-normal wrap-anywhere min-w-56' },
  },
  ...(multiRepository
    ? [{ accessorKey: 'repository', header: 'Repository', meta: { cell: 'text-muted-foreground' } }]
    : []),
  { id: 'pull', accessorFn: (m) => m.pull ?? 0, header: 'Pull request', meta: NUMBER },
  { accessorKey: 'lead', header: 'Lead', meta: NUMBER },
  { id: 'held', header: 'Held', enableSorting: false },
  {
    accessorKey: 'at',
    header: 'Merged',
    meta: { cell: `text-muted-foreground ${NOWRAP}` },
  },
])
const rowId = (m: Merged): string => `${m.repository}/${String(m.pull)}/${String(m.at)}`
</script>

<template>
  <DataTable
    :columns="columns"
    :data="rows"
    :row-id="rowId"
    caption="Recently merged"
    :default-sort="['at', 'desc']"
    prefix="merged_"
    :paged="{ label: 'merged pull requests', fallback: size }"
    :filter="{
      column: 'work',
      label: 'Filter merged pull requests',
      placeholder: 'Filter by ticket or title',
      none: 'merged pull request',
    }"
    hideable
    @shown="$emit('shown', $event)"
  >
    <template #cell-work="{ row: m }">
      <TicketHoverCard
        v-if="m.ticket"
        :repository="m.repository"
        :ticket="m.ticket"
        class="hover:underline"
        ><span class="font-mono text-muted-foreground">{{ m.ticket }}&nbsp;</span
        ><span class="font-medium">{{ m.title || m.branch }}</span></TicketHoverCard
      >
      <span v-else class="font-mono">{{ m.branch }}</span>
    </template>
    <template #cell-pull="{ row: m }">
      <a
        v-if="m.url"
        :href="m.url"
        class="underline-offset-4 hover:underline tabular-nums"
        target="_blank"
        rel="noopener noreferrer"
        >#{{ m.pull }}</a
      >
      <span v-else-if="m.pull !== null" class="tabular-nums">#{{ m.pull }}</span>
    </template>
    <template #cell-lead="{ row: m }">
      {{ span(m.lead)
      }}<span v-if="m.from === 'first_commit'" class="text-muted-foreground">
        from first commit</span
      >
    </template>
    <template #cell-held="{ row: m }">
      <span v-if="m.reverted" class="text-destructive">reverted </span>
      <span v-if="m.fixes.length"
        >fixed by
        <template v-for="(id, n) in m.fixes" :key="id"
          ><template v-if="n">, </template
          ><TicketHoverCard
            :repository="m.repository"
            :ticket="id"
            class="font-mono underline-offset-4 hover:underline"
            >{{ id }}</TicketHoverCard
          ></template
        ></span
      >
      <span v-if="m.checks === 'failed'" class="text-destructive"> checks failed</span>
      <span v-else-if="m.checks === 'none'" class="text-muted-foreground"> unchecked</span>
      <span v-else class="text-muted-foreground"> checks passed</span>
    </template>
    <template #cell-at="{ row: m }">{{ span(now - m.at) }} ago</template>
  </DataTable>
</template>
