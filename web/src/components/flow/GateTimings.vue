<script setup lang="ts">
import { ref } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { Analytics01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { ask } from '../../lib/actions'
import { refusalText } from '../../lib/notice'
import SectionCard from '../SectionCard.vue'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import DataTable from '../data-table/DataTable.vue'
import type { DataTableColumn } from '../data-table/features'
import { NUMBER } from '../data-table/look'

interface GateTiming {
  step: string
  runs: number
  median: number | null
  slowest: number | null
  budget: number | null
}

const columns: DataTableColumn<GateTiming>[] = [
  { accessorKey: 'step', header: 'Step' },
  { accessorKey: 'runs', header: 'Runs', meta: NUMBER },
  { accessorKey: 'median', header: 'Median', meta: NUMBER },
  { accessorKey: 'slowest', header: 'Slowest', meta: NUMBER },
  { accessorKey: 'budget', header: 'Budget', meta: NUMBER },
]
const expanded = ref(false)
const { data, error, isPending } = useQuery({
  queryKey: ['gate-timings'],
  queryFn: ({ signal }) => ask<GateTiming[]>('/api/gate-timings', signal),
  enabled: expanded,
})
const seconds = (value: number | null): string => (value === null ? '-' : `${String(value)} s`)
</script>

<template>
  <SectionCard
    heading="gate-timings-heading"
    title="Gate timings"
    :count="data?.length ?? null"
    :empty="expanded && data?.length === 0 && !error"
  >
    <template #empty>
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <HugeiconsIcon :icon="Analytics01Icon" aria-hidden="true" />
          </EmptyMedia>
          <EmptyTitle>No recorded gate timings</EmptyTitle>
          <EmptyDescription>Gate runs that report phase timings appear here.</EmptyDescription>
        </EmptyHeader>
      </Empty>
    </template>
    <Collapsible v-model:open="expanded">
      <CollapsibleTrigger as-child>
        <Button variant="outline" size="sm">Recent check runs and time budgets</Button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <p v-if="error" role="alert" class="mt-3 text-sm">{{ refusalText(error) }}</p>
        <p v-else-if="isPending" class="mt-3 text-sm">Reading gate timings…</p>
        <div v-else-if="data?.length" class="mt-3 overflow-x-auto">
          <p class="text-muted-foreground mb-2 text-sm">
            Latest 25 check runs with phase results across repositories
          </p>
          <DataTable
            :columns="columns"
            :data="data"
            :row-id="(row: GateTiming) => row.step"
            caption="Gate timings"
            prefix="gate_"
          >
            <template #cell-median="{ row }">
              {{ seconds(row.median) }}
              <span
                v-if="row.median !== null && row.budget !== null && row.median > row.budget"
                class="text-destructive ml-1"
                >Over budget</span
              >
            </template>
            <template #cell-slowest="{ row }">{{ seconds(row.slowest) }}</template>
            <template #cell-budget="{ row }">{{ seconds(row.budget) }}</template>
          </DataTable>
        </div>
      </CollapsibleContent>
    </Collapsible>
  </SectionCard>
</template>
