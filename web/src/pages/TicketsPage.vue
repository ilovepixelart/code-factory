<script setup lang="ts">
import FirstRun from '../components/FirstRun.vue'
import SectionCard from '../components/SectionCard.vue'
import {
  CheckListIcon,
  FilterIcon,
  KanbanIcon,
  PlusSignIcon,
  Search01Icon,
  UnfoldMoreIcon,
} from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { computed, inject, ref, useTemplateRef, watch } from 'vue'
import { useRoute } from 'vue-router'
import BoardColumn from '../components/BoardColumn.vue'
import BulkBar from '../components/BulkBar.vue'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import PageNav from '../components/PageNav.vue'
import ReadState from '../components/ReadState.vue'
import TicketPanel from '../components/TicketPanel.vue'
import TicketList from '../components/TicketList.vue'
import BoardNotices from '../components/board/BoardNotices.vue'
import FilterChips from '../components/board/FilterChips.vue'
import FilterMenu from '../components/board/FilterMenu.vue'
import { STAGES, type Column } from '../lib/board'
import { useBoardGestures } from '../lib/boardGestures'
import { folded, standing, toggle, type Choices } from '../lib/folding'
import { usePaged } from '../lib/paging'
import { BOARD } from '../lib/live'
import { NEW_TICKET } from '../lib/openTicket'
import * as selection from '../lib/selection'
import { dragging } from '../lib/sortable'
import { useTicketQuery } from '../lib/ticketQuery'
import { groupLanes, shown, sortCards } from '../lib/view'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { InputGroup, InputGroupAddon, InputGroupInput } from '@/components/ui/input-group'
import { Kbd } from '@/components/ui/kbd'

const route = useRoute()
const live = inject(BOARD)
const openNew = inject(NEW_TICKET, () => undefined)
live?.follow()
const board = computed(() => live?.board.value ?? null)
const isList = computed(() => route.meta.list === true)

const {
  query,
  lanes,
  sort,
  direction,
  needle,
  chips,
  clearUrl,
  boardUrl,
  listUrl,
  toggleUrl,
  lanesUrl,
  sortUrl,
} = useTicketQuery()

const columns = computed(() => (board.value ? shown(board.value, query.value, needle.value) : null))
const laneRows = computed(() =>
  columns.value && lanes.value ? groupLanes(columns.value, lanes.value) : null,
)
const rows = computed(() =>
  columns.value
    ? sortCards(
        STAGES.flatMap((s) => columns.value?.[s] ?? []),
        sort.value,
        direction.value,
      )
    : [],
)

// The list view draws one page of the board it already holds (CF-1191).
const paged = usePaged(() => (isList.value && columns.value ? rows.value : null))

const boardEmpty = computed(
  () => columns.value !== null && STAGES.every((s) => !columns.value?.[s].length),
)
const firstRun = computed(() => boardEmpty.value && !chips.value.length && !needle.value)

const choices = ref<Choices>({})
// A saved fold follows the cards the board holds, not those a filter leaves.
watch(
  board,
  (now) => {
    if (now)
      choices.value = standing(Object.fromEntries(STAGES.map((s) => [s, now.columns[s].length])))
  },
  { immediate: true },
)
function fold(stage: Column): void {
  choices.value = toggle(stage, columns.value?.[stage].length ?? 0)
}

// A selection keeps only the cards shown: on the list, the cards of its page (CF-1191).
watch([columns, isList, paged.rows], ([shown, list, page]) => {
  if (!shown) return
  const cards = list ? page : Object.values(shown).flat()
  selection.keepPresent(
    selection.chosen,
    cards.map((c) => selection.keyOf(c.repository, c.id)),
  )
})
const search = useTemplateRef<{ $el: HTMLInputElement }>('search')
const panel = useTemplateRef<InstanceType<typeof TicketPanel>>('panel')
const { panStart } = useBoardGestures({
  openPanel: (repository, ticket) => panel.value?.open(repository, ticket),
  focusSearch: () => search.value?.$el.focus(),
})
</script>

<template>
  <Teleport to="#header-controls">
    <Tabs :model-value="isList ? 'list' : 'board'" activation-mode="manual">
      <TabsList aria-label="View">
        <TabsTrigger value="board" as-child>
          <RouterLink :to="boardUrl" :aria-current="isList ? undefined : 'page'"
            ><HugeiconsIcon :icon="KanbanIcon" aria-hidden="true" />Board</RouterLink
          >
        </TabsTrigger>
        <TabsTrigger value="list" as-child>
          <RouterLink :to="listUrl" :aria-current="isList ? 'page' : undefined"
            ><HugeiconsIcon :icon="CheckListIcon" aria-hidden="true" />List</RouterLink
          >
        </TabsTrigger>
      </TabsList>
    </Tabs>
    <DropdownMenu v-if="!isList">
      <DropdownMenuTrigger as-child>
        <Button variant="ghost" class="gap-1.5">
          <HugeiconsIcon :icon="UnfoldMoreIcon" data-icon="inline-start" aria-hidden="true" /><span
            class="max-sm:sr-only"
            >Lanes<template v-if="lanes">: {{ lanes }}</template></span
          >
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" class="w-44" aria-label="Lanes">
        <DropdownMenuGroup>
          <DropdownMenuItem
            v-for="[value, label] in [
              ['', 'None'],
              ['repository', 'Repository'],
              ['assignee', 'Assignee'],
            ]"
            :key="value"
            as-child
          >
            <RouterLink
              :to="lanesUrl(value ?? '')"
              :aria-current="lanes === value ? 'true' : undefined"
              >{{ label }}</RouterLink
            >
          </DropdownMenuItem>
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
    <InputGroup class="w-44 max-sm:order-last max-sm:w-full xl:w-72">
      <InputGroupInput
        id="card-search"
        ref="search"
        :model-value="needle"
        type="search"
        aria-label="Filter cards"
        placeholder="Filter cards"
        @update:model-value="needle = String($event)"
      />
      <InputGroupAddon>
        <HugeiconsIcon :icon="Search01Icon" aria-hidden="true" />
      </InputGroupAddon>
      <InputGroupAddon align="inline-end" class="max-sm:hidden">
        <Kbd>/</Kbd>
      </InputGroupAddon>
    </InputGroup>
    <FilterMenu
      :query="query"
      :options="board?.options ?? {}"
      :toggle-url="toggleUrl"
      :clear-url="clearUrl"
    />
    <Button v-if="!firstRun" type="button" class="gap-1.5" @click="openNew()">
      <HugeiconsIcon :icon="PlusSignIcon" data-icon="inline-start" aria-hidden="true" /><span
        class="max-sm:sr-only"
        >New ticket</span
      >
      <Kbd class="max-sm:hidden">n</Kbd>
    </Button>
  </Teleport>
  <div class="flex h-full flex-col">
    <FilterChips v-if="chips.length" :chips="chips" :clear-url="clearUrl" />
    <div
      data-js-tickets-content
      class="page-wide flex min-h-0 flex-1 flex-col"
      :class="{ 'pb-20 max-md:pb-32': selection.chosen.size }"
    >
      <template v-if="board && columns">
        <FirstRun v-if="firstRun" />
        <SectionCard v-else-if="boardEmpty" heading="tickets-heading" title="Tickets" empty>
          <template #empty>
            <Empty>
              <EmptyHeader>
                <EmptyMedia variant="icon"
                  ><HugeiconsIcon :icon="FilterIcon" aria-hidden="true"
                /></EmptyMedia>
                <EmptyTitle>No tickets match the filter.</EmptyTitle>
                <EmptyDescription>Clear a filter or try a different search.</EmptyDescription>
              </EmptyHeader>
            </Empty>
          </template>
        </SectionCard>
        <template v-else-if="isList">
          <TicketList
            :rows="paged.rows.value"
            :sort="sort"
            :direction="direction"
            :sort-url="sortUrl"
          />
          <PageNav
            label="tickets"
            :total="paged.total.value"
            :page="paged.page.value"
            :size="paged.size.value"
          />
        </template>
        <template v-else>
          <div
            data-board-columns
            class="flex min-h-0 flex-1 items-stretch gap-3 overflow-x-auto"
            data-js-pan
            @pointerdown="panStart($event)"
          >
            <BoardColumn
              v-for="stage in STAGES"
              :key="stage"
              :stage="stage"
              :cards="columns[stage]"
              :total="board.totals[stage]"
              :limit="board.limits[stage]"
              :collapsed="!dragging && folded(stage, columns[stage].length, choices)"
              :lanes="laneRows"
              :today="board.today"
              @toggle="fold(stage)"
            />
          </div>
          <BoardNotices :problems="board.problems" />
        </template>
      </template>
      <ReadState
        v-else-if="live?.failed.value"
        what="the board"
        :failed="live.failed.value"
        @retry="void live.refresh()"
      />
      <Empty v-else class="flex-none">
        <EmptyHeader>
          <EmptyMedia variant="icon"><Spinner /></EmptyMedia>
          <EmptyTitle>Loading the board</EmptyTitle>
        </EmptyHeader>
      </Empty>
    </div>
  </div>
  <BulkBar v-if="selection.chosen.size" />
  <TicketPanel ref="panel" />
</template>
