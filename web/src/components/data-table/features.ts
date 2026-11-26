// The TanStack Table v9 features every data table shares, as shadcn-vue's Data Table guide
// declares them; row expanding is left out since no table expands, and v9 drops what is not named.

import {
  columnFilteringFeature,
  columnVisibilityFeature,
  createFilteredRowModel,
  createPaginatedRowModel,
  createSortedRowModel,
  filterFn_includesString,
  metaHelper,
  rowPaginationFeature,
  rowSelectionFeature,
  rowSortingFeature,
  sortFn_alphanumeric,
  sortFn_basic,
  sortFn_text,
  tableFeatures,
  type ColumnDef,
  type RowData,
} from '@tanstack/vue-table'

/** What a column adds to its cells and header: the classes the table's markup has always used. */
export interface ColumnLook {
  /** Classes on each of the column's cells. */
  cell?: string
  /** Classes on the column's header. */
  head?: string
  /** The column's name in the Columns menu, where its header is not plain text. */
  label?: string
  /** A cell's tooltip, from its row: none when it gives none. */
  title?: (row: never) => string | undefined
}

export const features = tableFeatures({
  columnFilteringFeature,
  columnVisibilityFeature,
  rowPaginationFeature,
  rowSelectionFeature,
  rowSortingFeature,
  filteredRowModel: createFilteredRowModel(),
  paginatedRowModel: createPaginatedRowModel(),
  sortedRowModel: createSortedRowModel(),
  filterFns: { includesString: filterFn_includesString },
  sortFns: { alphanumeric: sortFn_alphanumeric, basic: sortFn_basic, text: sortFn_text },
  columnMeta: metaHelper<ColumnLook>(),
})

export type DataTableFeatures = typeof features
export const SELECT = 'select'

/** A column of a data table over rows of `TData`. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- a column list mixes cell value types, as TanStack's own ColumnDef[] does
export type DataTableColumn<TData extends RowData> = ColumnDef<DataTableFeatures, TData, any>
