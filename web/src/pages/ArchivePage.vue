<script setup lang="ts">
import SectionCard from '../components/SectionCard.vue'
import { Archive02Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { useDebounceFn } from '@vueuse/core'
import { computed, h, inject, onScopeDispose, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import SearchBox from '../components/SearchBox.vue'
import ReadState from '../components/ReadState.vue'
import { act, ask } from '../lib/actions'
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/vue-query'
import { readAgain } from '../lib/queries'
import { keys } from '../lib/queryKeys'
import { STAGE_LABELS } from '../lib/board'
import { confirm } from '../lib/confirm'
import { day } from '../lib/format'
import { BOARD } from '../lib/live'
import {
  currentKind,
  currentSort,
  dateOf,
  sortUrl,
  type ArchivedRow,
  type PagedArchive,
} from '../lib/memory'
import { perform, refusalText } from '../lib/notice'
import { LIST_SIZE, fromAddress, linkTo } from '../lib/paging'
import { ticketHref } from '../lib/ticket'
import TicketHoverCard from '../components/TicketHoverCard.vue'
import ArchiveKinds from '../components/ArchiveKinds.vue'
import ArchiveRowActions from '../components/ArchiveRowActions.vue'
import StageGlyph from '../components/StageGlyph.vue'
import DataTable from '../components/data-table/DataTable.vue'
import type { DataTableColumn } from '../components/data-table/features'

// The archived tickets as a table, searched, sorted, filtered by kind and paged by the address; the
// server answers the page alone (CF-1191). Below the md breakpoint each row is a card (CF-1207).
const SEARCH_DELAY_MS = 200
const MUTED = 'text-muted-foreground max-md:order-4 max-md:p-0'
const COLUMNS: DataTableColumn<ArchivedRow>[] = [
  {
    accessorKey: 'id',
    header: 'ID',
    meta: {
      cell: 'font-mono whitespace-nowrap text-muted-foreground max-md:order-1 max-md:p-0',
    },
  },
  {
    accessorKey: 'title',
    header: 'Title',
    meta: {
      cell: 'min-w-40 font-medium whitespace-normal max-md:order-3 max-md:basis-full max-md:p-0',
    },
  },
  { accessorKey: 'type', header: 'Type', meta: { cell: MUTED } },
  { accessorKey: 'stage', header: 'Stage', meta: { cell: `whitespace-nowrap ${MUTED}` } },
  {
    id: 'archived',
    accessorFn: (row) => row.archived_at,
    header: 'Date',
    meta: {
      cell: 'whitespace-nowrap tabular-nums text-muted-foreground max-md:order-2 max-md:ml-auto max-md:p-0',
    },
  },
  { accessorKey: 'repository', header: 'Repository', meta: { cell: MUTED } },
  {
    id: 'actions',
    header: () => h('span', { class: 'sr-only' }, 'Actions'),
    enableSorting: false,
    meta: {
      cell: 'whitespace-nowrap text-right max-md:order-5 max-md:basis-full max-md:p-0 max-md:text-left',
    },
  },
]

const route = useRoute()
const router = useRouter()
// The Repository column only tells rows apart when the archive spans more than one repository.
const columns = computed(() =>
  new Set(archive.value?.rows.map((r) => r.repository)).size > 1
    ? COLUMNS
    : COLUMNS.filter(
        (c) => c.id !== 'repository' && !('accessorKey' in c && c.accessorKey === 'repository'),
      ),
)
const live = inject(BOARD)
const text = (key: string): string => {
  const value = route.query[key]
  return typeof value === 'string' ? value : ''
}
const typed = ref(text('q'))
const busy = ref(new Set<string>())
const query = computed(() => text('q'))
const current = computed(() => currentSort(text('sort'), text('dir')))
const kind = computed(() => currentKind(text('show')))
const address = computed(() =>
  Object.fromEntries(['q', 'sort', 'dir', 'size'].map((k) => [k, text(k)])),
)
const place = computed(() => fromAddress(route.query, '', LIST_SIZE))
// A search or a kind narrows the list of every archived ticket.
const narrowed = computed(() =>
  Boolean((query.value || kind.value) && archive.value?.archived_count),
)
const today = computed(() => live?.board.value?.today ?? dateOf(Date.now() / 1000))

// The archive is read under its address, so a new search, sort or page reads by itself; the rows
// shown stay until the next page answers. A read that fails takes the earlier answer away: its
// rows are not this query's.
const archiveAddress = computed(() => {
  const pairs = [
    ...['q', 'sort', 'dir'].map((k) => [k, text(k)]),
    ...(kind.value ? [['show', kind.value]] : []),
    ['page', String(place.value.page)],
    ['size', String(place.value.size)],
  ]
  return `/api/archive?${new URLSearchParams(pairs).toString()}`
})
const client = useQueryClient()
const archiveKey = computed(() => keys.archive(archiveAddress.value))
const archiveRead = useQuery({
  queryKey: archiveKey,
  queryFn: ({ signal }) => ask<PagedArchive>(archiveAddress.value, signal),
  placeholderData: keepPreviousData,
})
const archive = computed(() => archiveRead.data.value ?? null)
const failed = computed(() => (archiveRead.error.value ? refusalText(archiveRead.error.value) : ''))
const refresh = () => readAgain(client, archiveKey.value, archiveRead)
// A page past the last was served as the last: the address says which.
watch(
  archiveRead.dataUpdatedAt,
  () => {
    // Only the answer to this address says which page it served, not the one kept meanwhile.
    const answer = archiveRead.isPlaceholderData.value ? null : archive.value
    if (answer && text('page') && answer.page !== place.value.page)
      void router.replace({
        query: linkTo(route.query, '', answer.page, place.value.size, LIST_SIZE),
      })
  },
  { immediate: true },
)

// The box follows the address's `q`; a text the address already holds searches nothing.
watch(query, (addressed) => {
  if (addressed !== typed.value) typed.value = addressed
})
const search = useDebounceFn((value: string) => {
  if (value === query.value) return
  const kept =
    current.value[0] === 'archived' && current.value[1] === 'desc'
      ? {}
      : { sort: current.value[0], dir: current.value[1] }
  const shown = kind.value ? { show: kind.value } : {}
  const sized = text('size') ? { size: text('size') } : {}
  void router.replace({ query: { ...kept, ...shown, ...sized, ...(value ? { q: value } : {}) } })
}, SEARCH_DELAY_MS)
watch(typed, search)
onScopeDispose(search.cancel)

/** How a row left the board, in words. */
function how(row: ArchivedRow): string {
  if (row.stage !== 'released') return 'Archived by hand'
  return row.release ? `Released ${row.release}` : 'Released'
}

function base(row: ArchivedRow): string {
  return `/api/tickets/${encodeURIComponent(row.repository)}/${row.id}`
}

async function run(row: ArchivedRow, change: () => ReturnType<typeof act>): Promise<void> {
  busy.value.add(row.id)
  try {
    await perform(change, refresh)
  } finally {
    busy.value.delete(row.id)
  }
}

async function remove(row: ArchivedRow): Promise<void> {
  if (await confirm(`${row.id} ${row.title}`)) await run(row, () => act('DELETE', base(row)))
}
</script>

<template>
  <Teleport to="#header-controls">
    <form action="/archive" method="get" role="search" @submit.prevent>
      <SearchBox
        id="archive-search"
        v-model="typed"
        class="w-56 md:w-72"
        label="Search archived tickets"
        placeholder="Search by ID or title"
      />
    </form>
  </Teleport>
  <div v-if="archive" id="archive-table" class="page-wide">
    <SectionCard
      heading="archive-heading"
      title="Archived tickets"
      :count="archive.total"
      :description="narrowed ? `of ${archive.archived_count} archived` : ''"
      :empty="!archive.rows.length"
    >
      <template v-if="kind || archive.archived_count" #toolbar>
        <ArchiveKinds :kind="kind" :address="address" />
      </template>
      <template #empty>
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon"
              ><HugeiconsIcon :icon="Archive02Icon" aria-hidden="true"
            /></EmptyMedia>
            <EmptyTitle>{{
              !narrowed
                ? 'No archived tickets'
                : query
                  ? `No archived ticket matches “${query}”`
                  : kind === 'hand'
                    ? 'No ticket archived by hand'
                    : 'No released ticket'
            }}</EmptyTitle>
            <EmptyDescription>{{
              query
                ? 'Try a shorter search or clear it to see more tickets.'
                : narrowed
                  ? 'Switch to All to see every archived ticket.'
                  : 'Released tickets and tickets you archive from the board appear here.'
            }}</EmptyDescription>
          </EmptyHeader>
        </Empty>
      </template>
      <div class="flex flex-col gap-3">
        <DataTable
          v-if="archive.rows.length"
          :columns="columns"
          :data="archive.rows"
          :row-id="(row: ArchivedRow) => `${row.repository}/${row.id}`"
          :manual="{
            sort: current,
            sortHref: (key: string) => sortUrl(query, current, key, text('size'), kind),
          }"
          :row-attrs="(row: ArchivedRow) => ({ 'data-archived-row': row.id })"
          caption="Archived tickets"
          stacked
          :pager="{
            label: 'archived tickets',
            total: archive.total,
            page: archive.page,
            size: archive.size,
          }"
        >
          <template #cell-id="{ row }">
            <TicketHoverCard
              :repository="row.repository"
              :ticket="row.id"
              class="hover:underline"
              >{{ row.id }}</TicketHoverCard
            >
          </template>
          <template #cell-title="{ row }">
            <RouterLink :to="ticketHref(row.repository, row.id)" class="hover:underline">{{
              row.title
            }}</RouterLink>
          </template>
          <template #cell-stage="{ row }">
            <span class="flex flex-wrap items-center gap-x-1.5 md:flex-col md:items-start md:gap-0">
              <span class="inline-flex items-center gap-1.5"
                ><StageGlyph :stage="row.stage" decorative />{{ how(row) }}</span
              >
              <span v-if="row.stage !== 'released'" class="text-muted-foreground text-sm md:pl-5"
                >from {{ STAGE_LABELS[row.stage] }}</span
              >
            </span>
          </template>
          <template #cell-archived="{ row }">
            <template v-if="row.archived_at">{{
              day(dateOf(row.archived_at), '', today)
            }}</template>
            <span v-else class="text-muted-foreground">No date</span>
          </template>
          <template #cell-actions="{ row }">
            <ArchiveRowActions
              :id="row.id"
              :archived="row.archived"
              :busy="busy.has(row.id)"
              @restore="run(row, () => act('PATCH', base(row), { archived: '' }))"
              @remove="remove(row)"
            />
          </template>
        </DataTable>
      </div>
    </SectionCard>
  </div>
  <ReadState v-else shape="table" what="the archive" :failed="failed" @retry="void refresh()" />
</template>
