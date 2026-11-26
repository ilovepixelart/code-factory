<script setup lang="ts" generic="TData extends RowData">
import { HugeiconsIcon } from '@hugeicons/vue'
import { FlexRender, type RowData, type SortingState, type Table } from '@tanstack/vue-table'
import type { RouteLocationRaw } from 'vue-router'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ariaSortOf } from './address'
import { SELECT, type DataTableFeatures } from './features'
import { HEAD, SORT_ICON } from './look'

const { table, sort, sortHref, headerId } = defineProps<{
  table: Table<DataTableFeatures, TData>
  sort: SortingState[number] | undefined
  sortHref: (column: string) => RouteLocationRaw
  headerId: string
}>()
</script>

<template>
  <TableHeader :class="HEAD">
    <TableRow v-for="group in table.getHeaderGroups()" :key="group.id">
      <TableHead
        v-for="header in group.headers"
        :id="headerId ? `${headerId}-${header.column.id}` : undefined"
        :key="header.id"
        :class="header.column.columnDef.meta?.head"
        :aria-sort="ariaSortOf(sort, header.column.id)"
      >
        <template v-if="!header.isPlaceholder">
          <Checkbox
            v-if="header.column.id === SELECT"
            :model-value="
              table.getIsAllPageRowsSelected() ||
              (table.getIsSomePageRowsSelected() && 'indeterminate')
            "
            aria-label="Select every row on this page"
            @update:model-value="table.toggleAllPageRowsSelected(!!$event)"
          />
          <Button
            v-else-if="header.column.getCanSort()"
            variant="ghost"
            as-child
            data-header-sort
            class="text-sm"
          >
            <RouterLink :to="sortHref(header.column.id)">
              <FlexRender :header="header" />
              <HugeiconsIcon
                :icon="SORT_ICON[ariaSortOf(sort, header.column.id) ?? 'none']"
                data-slot="sort-icon"
                class="size-4"
                aria-hidden="true"
              />
            </RouterLink>
          </Button>
          <FlexRender v-else :header="header" />
        </template>
      </TableHead>
    </TableRow>
  </TableHeader>
</template>
