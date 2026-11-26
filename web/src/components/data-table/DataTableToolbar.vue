<script setup lang="ts">
import { ArrowDown01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { useId } from 'vue'
import type { RouteLocationRaw } from 'vue-router'
import SearchBox from '../SearchBox.vue'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { SORT_ICON } from './look'

// The toolbar of shadcn-vue's Data Table example above a table's bordered box: its filter on the
// left, its Columns menu on the right. Nothing shows while the table has neither.
const { filter, words, columns, sort } = defineProps<{
  filter: { label: string; placeholder: string } | null
  words: string
  /** The columns that can hide, by id with their name and whether they show; null for no menu. */
  columns: { id: string; name: string; visible: boolean }[] | null
  sort: {
    label: string
    ariaLabel: string
    columns: {
      id: string
      name: string
      to: RouteLocationRaw
      direction?: 'ascending' | 'descending' | undefined
    }[]
  } | null
}>()
const emit = defineEmits<{
  search: [words: string]
  show: [column: { id: string; visible: boolean }]
}>()
const filterId = useId()
</script>

<template>
  <div
    v-if="filter || columns || sort"
    data-slot="data-table-toolbar"
    class="flex flex-wrap items-center gap-2"
    :class="{ 'md:hidden': !filter && !columns }"
  >
    <div v-if="sort" class="md:hidden" data-mobile-sort>
      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <Button variant="outline" size="sm" :aria-label="sort.ariaLabel">
            {{ sort.label }}
            <HugeiconsIcon :icon="SORT_ICON.none" data-icon="inline-end" aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuItem v-for="column in sort.columns" :key="column.id" as-child>
            <RouterLink :to="column.to">
              {{ column.name }}
              <HugeiconsIcon
                v-if="column.direction"
                :icon="SORT_ICON[column.direction]"
                :aria-label="column.direction"
                role="img"
                class="ml-auto"
              />
            </RouterLink>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
    <SearchBox
      v-if="filter"
      :id="filterId"
      :model-value="words"
      class="max-w-sm"
      :label="filter.label"
      :placeholder="filter.placeholder"
      @update:model-value="emit('search', $event)"
    />
    <DropdownMenu v-if="columns">
      <DropdownMenuTrigger as-child>
        <Button variant="outline" class="ml-auto"
          >Columns<HugeiconsIcon :icon="ArrowDown01Icon" data-icon="inline-end" aria-hidden="true"
        /></Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuCheckboxItem
          v-for="column in columns"
          :key="column.id"
          :model-value="column.visible"
          @update:model-value="emit('show', { id: column.id, visible: !!$event })"
          >{{ column.name }}</DropdownMenuCheckboxItem
        >
      </DropdownMenuContent>
    </DropdownMenu>
  </div>
</template>
