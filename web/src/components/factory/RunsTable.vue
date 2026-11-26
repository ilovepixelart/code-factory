<script setup lang="ts">
import { ref } from 'vue'
import { share, type Runs } from '../../lib/factory'
import DataTable from '../data-table/DataTable.vue'
import type { DataTableColumn } from '../data-table/features'
import { AMOUNT } from '../data-table/look'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'

// The runs of the range counted by one of five keys, each with its share of all runs; the key is
// chosen in a tab strip, and the rows sort in the address under `runs_`.
const { runs } = defineProps<{ runs: Runs }>()

type Grouping = 'by_stage' | 'by_state' | 'by_source' | 'by_model' | 'by_agent'
type Row = Runs[Grouping][number]
const GROUPINGS: { value: Grouping; label: string }[] = [
  { value: 'by_stage', label: 'Stage' },
  { value: 'by_state', label: 'State' },
  { value: 'by_source', label: 'Source' },
  { value: 'by_model', label: 'Model' },
  { value: 'by_agent', label: 'Agent' },
]
const grouping = ref<Grouping>('by_stage')
const COLUMNS: DataTableColumn<Row>[] = [
  {
    id: 'key',
    accessorFn: (row) => row.key || 'unknown',
    header: 'Key',
    meta: { cell: 'font-mono whitespace-nowrap' },
  },
  { accessorKey: 'runs', header: 'Runs', meta: AMOUNT },
  { id: 'share', accessorFn: (row) => row.runs, header: 'Share', meta: AMOUNT },
]
</script>

<template>
  <div class="grid gap-3">
    <Tabs :model-value="grouping" @update:model-value="grouping = $event as Grouping">
      <TabsList aria-label="Group runs by">
        <TabsTrigger v-for="g in GROUPINGS" :key="g.value" :value="g.value">{{
          g.label
        }}</TabsTrigger>
      </TabsList>
    </Tabs>
    <DataTable
      :columns="COLUMNS"
      :data="runs[grouping]"
      :row-id="(row: Row) => row.key"
      caption="Runs"
      prefix="runs_"
    >
      <template #cell-share="{ row }">{{ share(row.runs, runs.total) }}</template>
    </DataTable>
  </div>
</template>
