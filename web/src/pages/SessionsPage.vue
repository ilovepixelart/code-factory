<script setup lang="ts">
import SectionCard from '../components/SectionCard.vue'
import { ItemGroup } from '@/components/ui/item'
import { Activity01Icon, File01Icon, Folder01Icon, Tick02Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { computed, inject, ref, watch } from 'vue'
import { useRoute, useRouter, type LocationQueryRaw } from 'vue-router'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import PageNav from '../components/PageNav.vue'
import ReadState from '../components/ReadState.vue'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import SessionCard from '../components/SessionCard.vue'
import SessionRow from '../components/SessionRow.vue'
import type { Card as BoardCard } from '../lib/board'
import { ask } from '../lib/actions'
import { BOARD } from '../lib/live'
import { refusalText } from '../lib/notice'
import { LIST_SIZE, fromAddress, linkTo } from '../lib/paging'
import { usePolledRead } from '../lib/queries'
import { keys, POLL } from '../lib/queryKeys'
import { loadText, saveText } from '../lib/storage'
import { STATE_FILTERS, filterOf, type StateFilter } from '../lib/session_view'
import { inRuns, type PagedSessions, type Usage } from '../lib/sessions'
import { Badge } from '@/components/ui/badge'
import { Field, FieldLabel } from '@/components/ui/field'
import { Switch } from '@/components/ui/switch'

// The sessions board: those waiting on the person first and whole, then a page of the rest by
// repository, as the server orders, filters by state and pages them (CF-1194, CF-1265); ended
// ones when asked. Follows changes.
const SHOW_ENDED = 'codeFactoryShowEnded'

const live = inject(BOARD)
live?.follow()
const route = useRoute()
const router = useRouter()
// None until the board first answers, so an empty board never reads as nothing waiting.
const now = ref(Date.now() / 1000)
const showEnded = ref(loadText(SHOW_ENDED) === '1')
const place = computed(() => fromAddress(route.query, '', LIST_SIZE))
const filter = computed(() => filterOf(route.query.state))

function address(): string {
  const pairs = [
    ['page', String(place.value.page)],
    ['size', String(place.value.size)],
    ...(filter.value ? [['state', filter.value]] : []),
    ...(showEnded.value ? [['ended', '1']] : []),
  ]
  return `/api/sessions?${new URLSearchParams(pairs).toString()}`
}

// Usage of the sessions the page shows, a read of their transcripts and of no others.
// None to read when none is shown: the route answers every session's usage for none named.
function usageAddress(listed: PagedSessions): string | null {
  const ids = [...listed.waiting, ...listed.rows].map((s) => ['session', s.session_id])
  return ids.length ? `/api/sessions/usage?${new URLSearchParams(ids).toString()}` : null
}

// The list is read under its address, so a new page, filter or the ended switch reads by itself.
const listed = usePolledRead(
  () => keys.sessions(address()),
  (signal) => ask<PagedSessions>(address(), signal),
  POLL.sessions,
)
const sessions = listed.data
const refresh = listed.refresh
// Once the board has answered, the page stands until the next tick reads it.
const failed = computed(() =>
  sessions.value === null && listed.query.error.value ? refusalText(listed.query.error.value) : '',
)
watch(
  listed.query.dataUpdatedAt,
  () => {
    const answer = sessions.value
    if (!answer) return
    now.value = Date.now() / 1000
    // A page past the last was served as the last: the address says which.
    if (route.query.page && answer.page !== place.value.page)
      void router.replace({
        query: linkTo(route.query, '', answer.page, place.value.size, LIST_SIZE),
      })
  },
  { immediate: true },
)
// Usage reads each shown transcript, seconds after a deploy: the list does not wait on it, and a
// usage read that fails leaves the last one shown.
const usageWhere = computed(() => (sessions.value ? usageAddress(sessions.value) : null))
const used = usePolledRead(
  () => keys.sessionUsage(usageWhere.value ?? ''),
  (signal) => ask<Record<string, Usage>>(usageWhere.value ?? '', signal),
  POLL.sessions,
  { ticks: () => usageWhere.value !== null },
)
const usage = computed(() => used.data.value ?? {})

function toggleEnded(): void {
  saveText(SHOW_ENDED, showEnded.value ? '1' : '0')
  const first = linkTo(route.query, '', 1, place.value.size, LIST_SIZE)
  if (route.query.page) void router.replace({ query: first })
}

const tickets = computed(() => {
  const found = new Map<string, BoardCard>()
  for (const cards of Object.values(live?.board.value?.columns ?? {})) {
    for (const card of cards) for (const s of card.sessions) found.set(s.session_id, card)
  }
  return found
})
const attention = computed(() =>
  filter.value && filter.value !== 'waiting' ? [] : (sessions.value?.waiting ?? []),
)
const groups = computed(() => inRuns(sessions.value?.rows ?? []))
function chipLink(state: StateFilter | null): { query: LocationQueryRaw } {
  const next: LocationQueryRaw = { ...route.query }
  delete next.page
  if (state) next.state = state
  else delete next.state
  return { query: next }
}
const stateOptions = computed(() => [
  { value: '', label: 'All', to: chipLink(null), count: undefined },
  ...STATE_FILTERS.map((state) => ({
    value: state,
    label: state,
    to: chipLink(state),
    count: sessions.value?.counts[state] ?? 0,
  })),
])
const hiddenEnded = computed(() => sessions.value?.ended_hidden ?? 0)
// The filter shows while it has sessions to narrow, or a state is chosen (the way back to All).
const anySession = computed(() =>
  Object.values(sessions.value?.counts ?? {}).some((count) => count > 0),
)
// The empty state's title and the sentence under it.
const noSessions = computed((): [string, string] => {
  if (filter.value) {
    return [
      `No ${filter.value} sessions`,
      'Choose another state or select All to see more sessions.',
    ]
  }
  if (hiddenEnded.value) {
    return [
      'No live sessions',
      `${String(hiddenEnded.value)} ended session${hiddenEnded.value === 1 ? ' is' : 's are'} hidden; turn on Show ended to list them.`,
    ]
  }
  return ['No sessions to show', 'Start an agent on a ticket and its session shows here.']
})
</script>

<template>
  <Teleport to="#header-controls">
    <Field orientation="horizontal" class="w-auto">
      <Switch id="show-ended" v-model="showEnded" @update:model-value="toggleEnded()" />
      <FieldLabel for="show-ended">Show ended</FieldLabel>
    </Field>
  </Teleport>
  <div v-if="sessions" id="sessions-region" class="page-wide">
    <!-- The page's toolbar: the state filter, over both sections. -->
    <nav
      v-if="filter || anySession"
      aria-label="Filter by state"
      class="mb-6 max-w-full overflow-x-auto overflow-y-hidden"
    >
      <Tabs :model-value="filter ?? ''" activation-mode="manual">
        <TabsList>
          <TabsTrigger
            v-for="option in stateOptions"
            :key="option.value"
            :value="option.value"
            as-child
          >
            <RouterLink
              :to="option.to"
              class="capitalize"
              :aria-current="(filter ?? '') === option.value ? 'page' : undefined"
              >{{ option.label
              }}<Badge v-if="option.count !== undefined" variant="outline">{{
                option.count
              }}</Badge></RouterLink
            >
          </TabsTrigger>
        </TabsList>
      </Tabs>
    </nav>
    <SectionCard
      v-if="!filter || filter === 'waiting'"
      class="mb-6"
      heading="attention-heading"
      title="Blocked sessions"
      :count="attention.length"
      description="longest wait first"
      :empty="!attention.length"
    >
      <template #empty>
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon"
              ><HugeiconsIcon :icon="Tick02Icon" aria-hidden="true"
            /></EmptyMedia>
            <EmptyTitle>No session is blocked</EmptyTitle>
            <EmptyDescription
              >Sessions that need an answer or permission appear here.</EmptyDescription
            >
          </EmptyHeader>
        </Empty>
      </template>
      <ItemGroup v-if="attention.length" class="gap-3" aria-label="Blocked sessions">
        <template v-for="(s, index) in attention" :key="s.session_id">
          <SessionCard
            :session="s"
            :usage="usage[s.session_id]"
            :now="now"
            :ticket="tickets.get(s.session_id)"
            :first="index === 0"
          />
        </template>
      </ItemGroup>
    </SectionCard>
    <SectionCard
      heading="sessions-heading"
      title="Sessions"
      :count="sessions.total"
      :description="filter ? `${filter}, by repository` : 'by repository, latest activity first'"
      :empty="filter !== 'waiting' && !groups.length"
    >
      <template #empty>
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon"
              ><HugeiconsIcon
                :icon="filter || hiddenEnded ? Activity01Icon : File01Icon"
                aria-hidden="true"
            /></EmptyMedia>
            <EmptyTitle>{{ noSessions[0] }}</EmptyTitle>
            <EmptyDescription>{{ noSessions[1] }}</EmptyDescription>
          </EmptyHeader>
        </Empty>
      </template>
      <template v-if="filter !== 'waiting'">
        <template v-for="([repository, items], index) in groups" :key="repository">
          <h3
            class="mb-2 flex items-center gap-2 text-sm font-medium"
            :class="{ 'mt-5': index > 0 }"
          >
            <HugeiconsIcon
              :icon="Folder01Icon"
              class="size-4 text-muted-foreground shrink-0"
              aria-hidden="true"
            />{{ repository
            }}<Badge variant="outline">{{ sessions.repositories[repository] ?? 0 }}</Badge>
          </h3>
          <ItemGroup class="gap-3" :aria-label="`Sessions in ${repository}`">
            <template v-for="s in items" :key="s.session_id">
              <SessionRow
                :session="s"
                :usage="usage[s.session_id]"
                :now="now"
                :ticket="tickets.get(s.session_id)"
                grouped
              />
            </template>
          </ItemGroup>
        </template>
        <PageNav
          label="sessions"
          :total="sessions.total"
          :page="sessions.page"
          :size="sessions.size"
        />
      </template>
    </SectionCard>
  </div>
  <ReadState v-else shape="table" what="the sessions" :failed="failed" @retry="void refresh()" />
</template>
