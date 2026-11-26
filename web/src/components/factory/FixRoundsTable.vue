<script setup lang="ts">
import type { FixRoundOutcome } from '../../lib/factory'
import SectionCard from '../SectionCard.vue'
import DataTable from '../data-table/DataTable.vue'
import type { DataTableColumn } from '../data-table/features'
import { NUMBER } from '../data-table/look'

const { rows } = defineProps<{ rows: FixRoundOutcome[] }>()
const columns: DataTableColumn<FixRoundOutcome>[] = [
  { accessorKey: 'rounds', header: 'Repair requests', meta: NUMBER },
  { accessorKey: 'merged', header: 'Merged', meta: NUMBER },
  { accessorKey: 'closed', header: 'Closed unmerged', meta: NUMBER },
  { accessorKey: 'open', header: 'Open', meta: NUMBER },
  { accessorKey: 'merge_rate', header: 'Merge rate', meta: NUMBER },
]
const percent = new Intl.NumberFormat(undefined, { style: 'percent', maximumFractionDigits: 1 })
</script>

<template>
  <SectionCard
    heading="fix-rounds-heading"
    title="Merge outcomes by repair round"
    :count="rows.length"
    description="Review returns and recorded CI or conflict rounds for PRs opened in this range. Merge rate uses merged and closed PRs."
  >
    <DataTable
      :columns="columns"
      :data="rows"
      :row-id="(row: FixRoundOutcome) => String(row.rounds)"
      caption="Pull request merge outcomes by repair round"
      prefix="fix_rounds_"
      stacked="labelled"
    >
      <template #cell-merge_rate="{ row }">
        {{ row.merge_rate === null ? '-' : percent.format(row.merge_rate) }}
      </template>
    </DataTable>
  </SectionCard>
</template>
