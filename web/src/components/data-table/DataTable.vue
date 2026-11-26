<script setup lang="ts" generic="TData extends RowData">
import {
  FlexRender,
  useTable,
  type Column,
  type RowData,
  type RowSelectionState,
  type SortingState,
  type Updater,
} from '@tanstack/vue-table'
import { Checkbox } from '@/components/ui/checkbox'
import { computed, shallowRef, useId, watch } from 'vue'
import { useRoute, useRouter, type RouteLocationRaw } from 'vue-router'
import { Table, TableBody, TableCell, TableRow } from '@/components/ui/table'
import { LIST_SIZE, usePaged, type Paged } from '../../lib/paging'
import { ariaSortOf, filterFrom, filterLink, sortFrom, sortLink, sortShown } from './address'
import { features, SELECT, type DataTableColumn, type DataTableFeatures } from './features'
import DataTableFooter from './DataTableFooter.vue'
import DataTableToolbar from './DataTableToolbar.vue'
import DataTableHead from './DataTableHead.vue'
import { FRAME, ROW, STACKED, TEXT } from './look'
import { useColumnVisibility } from './visibility'

// shadcn-vue's Data Table over TanStack Table v9, laid out as its example: a toolbar (filter left,
// Columns right) above the table's own bordered box, a footer (the selection left, Previous and
// Next right) under it. Its sort and page live in the address under `prefix` (CF-1191), so every
// sortable header and every page is a link.
const {
  columns,
  data,
  rowId,
  caption = '',
  defaultSort = null,
  prefix = '',
  paged = null,
  pager = null,
  hideable,
  columnsKey = '',
  filter = null,
  selected = null,
  rowLabel = null,
  manual = null,
  stacked = false,
  rowAttrs = null,
  frameClass = '',
  tableClass = '',
  headerClass = '',
  bodyClass = '',
  rowClass = '',
} = defineProps<{
  columns: DataTableColumn<TData>[]
  data: TData[]
  rowId: (row: TData) => string
  /** What the table is, for a screen reader: usually its section's title. */
  caption?: string
  /** The order the rows come in when the address names none, announced on its header. */
  defaultSort?: [string, 'asc' | 'desc'] | null
  prefix?: string
  /** Page the rows, `label` naming them under the table; unset, every row shows. */
  paged?: { label: string; fallback?: number } | null
  /** Rows the server paged: the footer pages them the same way, under `prefix`. */
  pager?: { label: string; total: number; page: number; size: number } | null
  /** A Columns menu over the table that shows or hides each column that can hide. */
  hideable?: boolean
  /** Where the columns a viewer hid are kept in this browser; unset, they reset on each visit. */
  columnsKey?: string
  /** A box over the table keeping the rows whose `column` holds its words; `none` names one row
   *  in the line shown when no row matches. */
  filter?: { column: string; label: string; placeholder: string; none?: string } | null
  /** The chosen rows by id: given, each row has a checkbox and the header one for its page.
   *  Ticking changes only the rows this table holds; any other id in the set stays. */
  selected?: Set<string> | null
  /** How a row's checkbox names it to a screen reader; its id by default. */
  rowLabel?: ((row: TData) => string) | null
  /** Rows already sorted and paged by the caller (the server, or a page that pages them): the
   *  current sort, and the link each sortable header goes to. */
  manual?: { sort: [string, string]; sortHref: (column: string) => RouteLocationRaw } | null
  /** Each row a card on phones. Labelled rows also show column names and a sort menu. */
  stacked?: boolean | 'labelled'
  /** Attributes on a row's `tr`. */
  rowAttrs?: ((row: TData) => Record<string, string>) | null
  /** Classes on the bordered box around the table, for a box that fills its caller. */
  frameClass?: string
  tableClass?: string
  headerClass?: string
  bodyClass?: string
  rowClass?: string
}>()

const emit = defineEmits<{
  /** The number of rows the filter keeps, for a section's count. */
  shown: [count: number]
}>()
defineSlots<Record<`cell-${string}`, (props: { row: TData }) => unknown>>()

const SELECT_COLUMN: DataTableColumn<TData> = {
  id: SELECT,
  enableSorting: false,
  enableHiding: false,
  meta: { head: 'w-8', cell: 'w-8' },
}

const route = useRoute()
const ids = computed(() =>
  columns.flatMap((c) => {
    const id = c.id ?? ('accessorKey' in c ? String(c.accessorKey) : '')
    return id ? [id] : []
  }),
)
const router = useRouter()
const sorting = computed<SortingState>(() =>
  manual
    ? [{ id: manual.sort[0], desc: manual.sort[1] === 'desc' }]
    : sortFrom(route.query, prefix, ids.value),
)
const headerLink = (column: string): RouteLocationRaw =>
  manual ? manual.sortHref(column) : { query: sortLink(route.query, prefix, column, sorting.value) }
const words = computed(() => filterFrom(route.query, prefix))
const columnFilters = computed(() =>
  filter && words.value ? [{ id: filter.column, value: words.value }] : [],
)
function search(typed: string): void {
  void router.replace({ query: filterLink(route.query, prefix, typed) })
}
const place = shallowRef<Paged<unknown>>()
const rowSelection = computed<RowSelectionState>(() => {
  const chosen = selected
  if (!chosen) return {}
  return Object.fromEntries(data.map(rowId).flatMap((id) => (chosen.has(id) ? [[id, true]] : [])))
})
// A table's storage key is fixed for its life, so reading it once is right.
// eslint-disable-next-line vue/no-setup-props-reactivity-loss -- the key is fixed for the table's life
const visibility = useColumnVisibility(columnsKey)

const table = useTable({
  features,
  get data() {
    return data
  },
  get columns() {
    return selected ? [SELECT_COLUMN, ...columns] : columns
  },
  state: computed(() => ({
    sorting: sorting.value,
    columnFilters: columnFilters.value,
    columnVisibility: visibility.state.value,
    rowSelection: rowSelection.value,
    pagination: {
      pageIndex: (place.value?.page.value ?? 1) - 1,
      pageSize: place.value?.size.value ?? LIST_SIZE,
    },
  })),
  // Unpaged, the table must not slice: its paginated row model would show the first ten rows.
  get manualPagination() {
    return !paged
  },
  get manualSorting() {
    return Boolean(manual)
  },
  get enableRowSelection() {
    return Boolean(selected)
  },
  onRowSelectionChange: choose,
  onColumnVisibilityChange: visibility.change,
  getRowId: (row: TData) => rowId(row),
})

/** The new selection written back to the caller's set, for the rows this table holds alone. */
function choose(next: Updater<RowSelectionState>): void {
  const chosen = selected
  if (!chosen) return
  const state = typeof next === 'function' ? next(rowSelection.value) : next
  for (const row of table.getCoreRowModel().rows) {
    if (state[row.id]) chosen.add(row.id)
    else chosen.delete(row.id)
  }
}

const rowName = (row: TData): string => (rowLabel ?? rowId)(row)
// A column's `title` is written for its own row type, which this table's TData is; the shared meta
// type cannot name TData, so it is narrowed here.
const cellTitle = (title: ((row: never) => string | undefined) | undefined, row: TData) =>
  (title as ((row: TData) => string | undefined) | undefined)?.(row)

// The page is counted over the sorted rows, so a sort orders the whole list before it is paged;
// the table reads it through `place`, filled once the page exists. A table's prefix and page size
// are fixed for its life, so reading them once is right.
// eslint-disable-next-line vue/no-setup-props-reactivity-loss -- prefix and size are fixed for the table's life
const page = usePaged(
  () => (paged ? table.getPrePaginatedRowModel().rows : []),
  prefix,
  paged?.fallback ?? LIST_SIZE,
)
place.value = page

/** Where the footer pages from: the table's own pages, or the server's. */
const pages = computed(() => {
  if (pager) return { ...pager, fallback: LIST_SIZE }
  if (!paged) return null
  return {
    label: paged.label,
    total: page.total.value,
    page: page.page.value,
    size: page.size.value,
    fallback: paged.fallback ?? LIST_SIZE,
  }
})
const kept = computed(() => table.getFilteredRowModel().rows)
const chosenCount = computed(() => kept.value.filter((r) => r.getIsSelected()).length)
watch(
  () => kept.value.length,
  (count) => {
    emit('shown', count)
  },
  { immediate: true },
)
const visibleCount = computed(() => table.getVisibleLeafColumns().length)

/** A column's name in the Columns menu: its label, else its header when that is text. */
function columnName(column: Column<DataTableFeatures, TData>): string {
  const { meta, header } = column.columnDef
  return meta?.label ?? (typeof header === 'string' ? header : column.id)
}
/** The columns the Columns menu lists: those that can hide, with whether each shows. */
const hiding = computed(() =>
  table
    .getAllColumns()
    .filter((c) => c.getCanHide())
    .map((c) => ({ id: c.id, name: columnName(c), visible: c.getIsVisible() })),
)

const shownSort = computed(() => sortShown(sorting.value, defaultSort))
const headerId = useId()
const columnHeaderId = (id: string) => `${headerId}-${id}`
const mobileSort = computed(() => {
  if (stacked !== 'labelled') return null
  const options = table.getVisibleLeafColumns().filter((column) => column.getCanSort())
  if (!options.length) return null
  const current = options.find((column) => column.id === shownSort.value?.id)
  const label = current ? `Sort by ${columnName(current)}` : 'Sort by column'
  return {
    label,
    ariaLabel: caption ? `${label} for ${caption}` : label,
    columns: options.map((column) => ({
      id: column.id,
      name: columnName(column),
      to: headerLink(column.id),
      direction: ariaSortOf(shownSort.value, column.id),
    })),
  }
})
</script>

<template>
  <div class="flex flex-col gap-4">
    <DataTableToolbar
      :filter="filter"
      :words="words"
      :columns="hideable ? hiding : null"
      :sort="mobileSort"
      @search="search($event)"
      @show="table.getColumn($event.id)?.toggleVisibility($event.visible)"
    />
    <!-- A table wider than its box scrolls inside it, the edge with more to show faded. -->
    <div
      data-slot="data-table-frame"
      class="*:data-[slot=table-container]:scroll-fade-x"
      :class="[FRAME, stacked ? STACKED.frame : '', frameClass]"
    >
      <Table :class="[TEXT, stacked ? STACKED.table : '', tableClass]">
        <caption v-if="caption" class="sr-only">
          {{
            caption
          }}
        </caption>
        <DataTableHead
          :table="table"
          :sort="shownSort"
          :sort-href="headerLink"
          :header-id="stacked === 'labelled' ? headerId : ''"
          :class="[stacked ? STACKED.header : '', headerClass]"
        />
        <TableBody :class="[stacked ? STACKED.body : '', bodyClass]">
          <TableRow
            v-for="row in table.getRowModel().rows"
            :key="row.id"
            v-bind="rowAttrs?.(row.original)"
            :class="[
              ROW,
              stacked ? STACKED.surface : '',
              stacked === 'labelled' ? STACKED.labelledRow : stacked ? STACKED.row : '',
              rowClass,
            ]"
            :data-state="row.getIsSelected() ? 'selected' : undefined"
          >
            <TableCell
              v-for="cell in row.getVisibleCells()"
              :key="cell.id"
              :class="[
                cell.column.columnDef.meta?.cell,
                stacked === 'labelled' ? STACKED.labelledCell : '',
              ]"
              :data-column-label="stacked === 'labelled' ? columnName(cell.column) : undefined"
              :headers="stacked === 'labelled' ? columnHeaderId(cell.column.id) : undefined"
              :title="cellTitle(cell.column.columnDef.meta?.title, row.original)"
            >
              <Checkbox
                v-if="cell.column.id === SELECT"
                :model-value="row.getIsSelected()"
                :aria-label="`Select ${rowName(row.original)}`"
                @update:model-value="row.toggleSelected(!!$event)"
              />
              <slot v-else :name="`cell-${cell.column.id}`" :row="row.original"
                ><FlexRender :cell="cell"
              /></slot>
            </TableCell>
          </TableRow>
          <TableRow v-if="filter && words && !kept.length">
            <TableCell :colspan="visibleCount" class="h-24 text-center text-muted-foreground">
              No {{ filter.none ?? 'row' }} matches “{{ words }}”
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>
    <DataTableFooter
      :chosen="selected ? chosenCount : null"
      :rows="kept.length"
      :pages="pages"
      :prefix="prefix"
    />
  </div>
</template>
