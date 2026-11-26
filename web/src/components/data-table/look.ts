import { ArrowDown02Icon, ArrowUp02Icon, ArrowUpDownIcon } from '@hugeicons/core-free-icons'

// The look every table shares with shadcn-vue's Data Table example, for the shared DataTable and
// for the few plain Tables that are too short to need it.

/** The shared surface for a table, including its header. */
export const FRAME = 'overflow-hidden rounded-xl bg-card'

/** The shared table uses spacing between rows, including inside the generated header. */
export const TEXT = 'text-sm [&_tr[data-slot=table-row]]:border-0'

/** A header row: the cells' size, whether a column sorts or not, as in the example. */
export const HEAD = 'bg-muted text-sm'

/** A body row's height: the example's 48 px rows. */
export const ROW = 'h-12'

/** An amount (a count, a cost, a share): right-aligned, figures of one width, medium weight. */
export const AMOUNT = { head: 'text-right', cell: 'text-right font-medium tabular-nums' }

/** Any other figure (a number, a duration, an age): right-aligned in figures of one width. */
export const NUMBER = { head: 'text-right', cell: 'text-right tabular-nums whitespace-nowrap' }

/** A table whose rows turn into cards below 768 px, as the Archive's do (CF-1207). */
export const STACKED = {
  frame: 'max-md:rounded-none max-md:bg-transparent',
  table: 'max-md:block',
  header: 'max-md:hidden',
  body: 'max-md:grid max-md:gap-3',
  surface: 'max-md:rounded-2xl max-md:bg-card max-md:shadow-xs',
  // A card's cells sit on its own padding, not each on a table cell's.
  row: 'max-md:h-auto max-md:flex max-md:flex-wrap max-md:items-center max-md:gap-x-3 max-md:gap-y-1 max-md:px-4 max-md:py-3 max-md:*:p-0',
  labelledRow:
    'max-md:h-auto max-md:grid max-md:grid-cols-2 max-md:items-start max-md:gap-x-4 max-md:gap-y-3 max-md:px-4 max-md:py-3 max-md:*:p-0',
  labelledCell:
    'max-md:min-w-0 max-md:whitespace-normal max-md:wrap-anywhere max-md:text-left max-md:first:col-span-2 max-md:first:font-semibold',
}

/** A sortable header's icon: the example's up-down mark, or the direction it is sorted in. */
export const SORT_ICON = {
  descending: ArrowDown02Icon,
  ascending: ArrowUp02Icon,
  none: ArrowUpDownIcon,
}
