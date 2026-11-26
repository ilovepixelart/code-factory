<script setup lang="ts">
import SectionCard from './SectionCard.vue'
import { computed, useTemplateRef, watch } from 'vue'
import { STAGE_LABELS } from '../lib/board'
import { useAction } from '../lib/notice'
import { type AgentList, runOrder } from '../lib/roster'
import { Button } from '@/components/ui/button'
import { FieldError } from '@/components/ui/field'
import DataTable from './data-table/DataTable.vue'
import type { DataTableColumn } from './data-table/features'

// The order in which each column's runs take its agents, and the buttons that change it (CF-915).
const { list } = defineProps<{ list: AgentList }>()
const emit = defineEmits<{ changed: [] }>()

const columns = computed(() =>
  runOrder(list).map(({ column, agents }) => ({
    column,
    rows: agents.map((agent, index) => ({
      name: agent.name,
      position: index + 1,
      last: index === agents.length - 1,
    })),
  })),
)
type OrderRow = (typeof columns.value)[number]['rows'][number]
const TABLE_COLUMNS: DataTableColumn<OrderRow>[] = [
  {
    accessorKey: 'position',
    header: 'Order',
    enableSorting: false,
    meta: { cell: 'w-12 text-muted-foreground tabular-nums' },
  },
  {
    accessorKey: 'name',
    header: 'Agent',
    enableSorting: false,
    meta: { cell: 'whitespace-normal wrap-anywhere font-medium' },
  },
  {
    id: 'actions',
    header: 'Actions',
    enableSorting: false,
    meta: { head: 'text-right', cell: 'w-24' },
  },
]
const rowId = (row: OrderRow) => row.name
const { busy, error, send } = useAction()

// The press whose answer has not yet reordered the lists: a reorder moves the pressed row's
// nodes, which drops focus, so focus is put back on it once the lists are drawn.
type Direction = 'up' | 'down'
let pressed: { name: string; column: string; direction: Direction } | null = null
const root = useTemplateRef<{ $el: HTMLElement }>('root')

// The pressed control, or the row's other one when this edge row has no further move that way.
function refocus({ name, column, direction }: NonNullable<typeof pressed>): void {
  // Focus on a control that has just become disabled is dropped to the body only at the next
  // frame, so such a control counts as focus already lost.
  const active = document.activeElement
  if (active && active !== document.body && !active.matches(':disabled')) return
  const other = direction === 'up' ? 'down' : 'up'
  const buttons = [...(root.value?.$el.querySelectorAll('button') ?? [])]
  const labelled = (d: Direction) =>
    buttons.find((b) => b.getAttribute('aria-label') === `Move ${name} ${d} in ${column}`)
  const target = [labelled(direction), labelled(other)].find((b) => b && !b.disabled)
  target?.focus()
}

watch(
  columns,
  () => {
    if (pressed) refocus(pressed)
    pressed = null
  },
  { flush: 'post' },
)

// Busy is `aria-disabled`, not `disabled`, so the pressed button keeps focus while it is sent.
async function move(name: string, column: string, direction: Direction): Promise<void> {
  if (busy.value) return
  pressed = { name, column, direction }
  await send(
    'POST',
    `/api/agent-definitions/${encodeURIComponent(name)}/move`,
    { column, direction },
    () => {
      emit('changed')
    },
  )
  if (error.value) pressed = null
}
</script>

<template>
  <SectionCard
    ref="root"
    heading="run-order"
    title="Run order"
    description="a run takes the first free agent"
  >
    <FieldError v-if="error" class="mb-3">{{ error }}</FieldError>
    <div class="grid grid-cols-1 gap-5 lg:grid-cols-3">
      <div v-for="entry in columns" :key="entry.column" class="min-w-0" data-run-order>
        <h3 class="text-xs font-medium tracking-wider text-muted-foreground uppercase mb-2">
          {{ STAGE_LABELS[entry.column] }}
        </h3>
        <DataTable
          :columns="TABLE_COLUMNS"
          :data="entry.rows"
          :row-id="rowId"
          :caption="`${STAGE_LABELS[entry.column]} run order`"
        >
          <template #cell-actions="{ row }">
            <div class="flex justify-end gap-1">
              <Button
                type="button"
                variant="ghost"
                size="xs"
                :aria-label="`Move ${row.name} up in ${entry.column}`"
                :aria-disabled="busy"
                :disabled="row.position === 1"
                @click="move(row.name, entry.column, 'up')"
                >Up</Button
              >
              <Button
                type="button"
                variant="ghost"
                size="xs"
                :aria-label="`Move ${row.name} down in ${entry.column}`"
                :aria-disabled="busy"
                :disabled="row.last"
                @click="move(row.name, entry.column, 'down')"
                >Down</Button
              >
            </div>
          </template>
        </DataTable>
      </div>
    </div>
  </SectionCard>
</template>
