<script setup lang="ts">
import { share, type RoleNoteOutcome } from '../../lib/factory'
import SectionCard from '../SectionCard.vue'
import DataTable from '../data-table/DataTable.vue'
import type { DataTableColumn } from '../data-table/features'
import { NUMBER } from '../data-table/look'

const { rows } = defineProps<{ rows: RoleNoteOutcome[] }>()
const columns: DataTableColumn<RoleNoteOutcome>[] = [
  { accessorKey: 'role', header: 'Role' },
  { accessorKey: 'notes', header: 'Notes', meta: NUMBER },
  { accessorKey: 'fixed', header: 'Linked to a fix', meta: NUMBER },
  {
    id: 'share',
    accessorFn: (row) => row.fixed / row.notes,
    header: 'Share linked to a fix',
    meta: NUMBER,
  },
]
</script>

<template>
  <SectionCard
    heading="role-notes-heading"
    title="Review role notes"
    :count="rows.length"
    description="Notes posted in this range. A note counts as linked to a fix when its finding is marked fixed."
  >
    <DataTable
      :columns="columns"
      :data="rows"
      :row-id="(row: RoleNoteOutcome) => row.role"
      caption="Review role notes linked to fixes"
      prefix="role_notes_"
      stacked="labelled"
    >
      <template #cell-share="{ row }">{{ share(row.fixed, row.notes) }}</template>
    </DataTable>
  </SectionCard>
</template>
