<script setup lang="ts">
import SectionCard from '../components/SectionCard.vue'
import { PlusSignIcon, Tick02Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { useDebounceFn } from '@vueuse/core'
import { computed, nextTick, onScopeDispose, ref, useTemplateRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import SearchBox from '../components/SearchBox.vue'
import MemoryAgentProposals from '../components/MemoryAgentProposals.vue'
import MemoryEntry from '../components/MemoryEntry.vue'
import MemoryGroup from '../components/MemoryGroup.vue'
import MemoryFlags from '../components/MemoryFlags.vue'
import MemoryHistory from '../components/MemoryHistory.vue'
import MemoryForm, { type MemoryDraft } from '../components/MemoryForm.vue'
import MemoryMeter from '../components/MemoryMeter.vue'
import MemoryProposals from '../components/MemoryProposals.vue'
import MemoryQueue from '../components/MemoryQueue.vue'
import MemoryResults from '../components/MemoryResults.vue'
import ReadState from '../components/ReadState.vue'
import { act, ask } from '../lib/actions'
import { clock, thousands } from '../lib/format'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { readAgain } from '../lib/queries'
import { keys } from '../lib/queryKeys'
import { LIST_SIZE, fromAddress } from '../lib/paging'
import { type LoadGroup, type Memory, loadGroups, reviewDue, sizeOf } from '../lib/memory'
import { announce, refusalText, undone } from '../lib/notice'
import { Button } from '@/components/ui/button'
import { Field, FieldLabel } from '@/components/ui/field'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'

// What the factory remembers, reviewed in place, and a search of what the repository knows: what
// loads against its budget and the entries without a why, which `?why=none` lists alone, then what
// needs the owner, then the entries by where they load (CF-1171, CF-1195). The search results are
// paged by the server, the groups in the browser.
const SEARCH_DELAY_MS = 200

const route = useRoute()
const router = useRouter()
const typed = ref(typeof route.query.q === 'string' ? route.query.q : '')
const query = computed(() => (typeof route.query.q === 'string' ? route.query.q.trim() : ''))
const active = computed(() =>
  memory.value
    ? [
        ...memory.value.unreviewed,
        ...memory.value.rules,
        ...memory.value.decisions,
        ...memory.value.lessons,
      ]
    : [],
)
const due = computed(() => reviewDue(active.value, memory.value?.review_queue ?? []))
const overdue = computed(() => new Set((memory.value?.review_queue ?? []).map(keyOf)))
const proposed = computed(() => active.value.filter((r) => r.proposed))
const waiting = computed(
  () =>
    proposed.value.length +
    (memory.value?.pairs.length ?? 0) +
    (memory.value?.proposals.length ?? 0) +
    due.value.length,
)
const dueHint = computed(() => {
  const sourceless = due.value.filter((r) => r.source.trim() === '').length
  return sourceless ? `${String(sourceless)} with no source` : ''
})
const GROUPS: Record<LoadGroup, [string, (size: number) => string]> = {
  core: ['Core', (size) => `every session, ${thousands(size)} characters`],
  spec: ['Spec', (size) => `spec runs, ${thousands(size)} characters`],
  build: ['Build', (size) => `build runs, ${thousands(size)} characters`],
  review: ['Review', (size) => `review runs, ${thousands(size)} characters`],
  paths: [
    'Paths',
    (size) => `sessions changing a matching path, up to ${thousands(size)} characters`,
  ],
  archive: ['Archive', () => 'searched on demand, listed in the index of recall'],
  off: ['Not loaded', () => 'a test enforces each, or another entry supersedes it'],
}
const bare = computed(() => active.value.filter((r) => !r.proposed && r.why.trim() === ''))
const onlyBare = computed(() => route.query.why === 'none')
const groups = computed(() =>
  loadGroups(onlyBare.value ? bare.value : active.value).filter(([, rows]) => rows.length),
)
// The address with the filter flipped and every group back on its first page.
const filterTo = computed(() => {
  const kept = Object.fromEntries(
    Object.entries(route.query).filter(([key]) => key !== 'why' && !key.endsWith('-page')),
  )
  return { query: onlyBare.value ? kept : { ...kept, why: 'none' } }
})
const hashed = computed(() => decodeURIComponent(route.hash.slice(1)))
const keyOf = (r: { repository: string; id: string }): string => `${r.repository}/${r.id}`
const repository = ref('')

const adding = ref(false)
const addButton = useTemplateRef('addButton')
const addBusy = ref(false)
const addError = ref('')
const blank: MemoryDraft = { kind: 'rule', statement: '', why: '', source: '', guard: '' }

async function add(draft: MemoryDraft): Promise<void> {
  addBusy.value = true
  addError.value = ''
  try {
    const into = repository.value === '' ? (memory.value?.repositories[0] ?? '') : repository.value
    announce(await act('POST', '/api/memory', { repository: into, ...draft }))
    closeAdd()
  } catch (error_) {
    addError.value = refusalText(error_)
  }
  addBusy.value = false
  await refresh()
}

// The form's fields leave with it: the keyboard goes back to the button that opened it.
function closeAdd(): void {
  adding.value = false
  void nextTick(() => addButton.value?.$el.focus())
}

function openAdd(): void {
  addError.value = ''
  repository.value = memory.value?.repositories[0] ?? ''
  adding.value = true
}

// The search is read under its address, so a new text or page reads by itself. A read that fails
// takes the earlier answer away: its results are not this query's.
const memoryAddress = computed(() => {
  const place = fromAddress(route.query, '', LIST_SIZE)
  const asked = { q: query.value, page: String(place.page), size: String(place.size) }
  return `/api/memory?${new URLSearchParams(asked).toString()}`
})
const client = useQueryClient()
const memoryKey = computed(() => keys.memory(memoryAddress.value))
const memoryRead = useQuery({
  queryKey: memoryKey,
  queryFn: ({ signal }) => ask<Memory>(memoryAddress.value, signal),
})
const memory = computed(() => memoryRead.data.value ?? null)
const failed = computed(() => (memoryRead.error.value ? refusalText(memoryRead.error.value) : ''))
const refresh = () => readAgain(client, memoryKey.value, memoryRead)
watch(undone, () => void refresh())

// The box follows the address's `q`; a text the address already holds searches nothing.
const addressed = computed(() => (typeof route.query.q === 'string' ? route.query.q : ''))
watch(addressed, (text) => {
  if (text !== typed.value) typed.value = text
})
const search = useDebounceFn((text: string) => {
  if (text !== addressed.value) void router.replace({ query: text ? { q: text } : {} })
}, SEARCH_DELAY_MS)
watch(typed, search)
onScopeDispose(search.cancel)
</script>

<template>
  <Teleport to="#header-controls">
    <form
      action="/memory"
      method="get"
      role="search"
      class="max-sm:order-last max-sm:w-full"
      @submit.prevent
    >
      <SearchBox
        id="memory-search"
        v-model="typed"
        class="w-56 max-sm:w-full md:w-72"
        label="Search what the repository knows"
        placeholder="Search docs, tickets, memory"
      />
    </form>
    <Button ref="addButton" type="button" @click="openAdd()">
      <HugeiconsIcon :icon="PlusSignIcon" data-icon="inline-start" aria-hidden="true" />Add an entry
    </Button>
  </Teleport>
  <div v-if="memory" class="page-wide grid grid-cols-1 gap-6 wrap-anywhere">
    <MemoryMeter
      :active="active"
      :loaded="memory.loaded_chars"
      :ceiling="memory.ceiling"
      :rules-over="memory.rules_over ?? 0"
    >
      <Button
        v-if="bare.length || onlyBare"
        as-child
        :variant="onlyBare ? 'secondary' : 'ghost'"
        size="xs"
        :aria-pressed="onlyBare"
        ><RouterLink :to="filterTo">{{ bare.length }} without a why</RouterLink></Button
      >
    </MemoryMeter>
    <div v-if="query" id="memory-results">
      <MemoryResults :memory="memory" :query="query" />
    </div>
    <Alert v-if="memory.filing" variant="destructive">
      <AlertDescription>
        Memory changes were not filed at {{ clock(memory.filing.at) }}: {{ memory.filing.outcome }}.
        <code>code-factory land {{ memory.filing.worktree }}</code> lands them by hand.
      </AlertDescription>
    </Alert>
    <SectionCard v-if="adding" heading="memory-adding" title="Add an entry">
      <Field v-if="memory.repositories.length > 1" class="mb-2">
        <FieldLabel for="memory-add-repository">Repository</FieldLabel>
        <NativeSelect
          id="memory-add-repository"
          :model-value="repository"
          class="w-full"
          @update:model-value="repository = String($event)"
        >
          <NativeSelectOption v-for="name in memory.repositories" :key="name" :value="name">
            {{ name }}
          </NativeSelectOption>
        </NativeSelect>
      </Field>
      <MemoryForm
        name="Add an entry"
        :start="blank"
        submit="Add"
        require-source
        :error="addError"
        :busy="addBusy"
        @save="add($event)"
        @cancel="closeAdd()"
      />
    </SectionCard>
    <MemoryAgentProposals v-if="proposed.length" :proposed="proposed" @changed="refresh()" />
    <MemoryFlags
      v-if="memory.pairs.length"
      :pairs="memory.pairs"
      :active="active"
      @changed="refresh()"
    />
    <MemoryProposals
      v-if="memory.proposals.length"
      :proposals="memory.proposals"
      @changed="refresh()"
    />
    <MemoryQueue
      v-if="due.length"
      id="memory-review-due"
      title="Review due"
      :hint="dueHint"
      :rows="due"
      :key-of="keyOf"
    >
      <template #row="{ row }">
        <MemoryEntry
          :record="row"
          :others="active"
          variant="due"
          :overdue="overdue.has(keyOf(row))"
          @changed="refresh()"
        />
      </template>
    </MemoryQueue>
    <SectionCard v-if="!waiting" key="waiting" heading="memory-waiting" title="To review" empty>
      <template #empty>
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon"
              ><HugeiconsIcon :icon="Tick02Icon" aria-hidden="true"
            /></EmptyMedia>
            <EmptyTitle>Nothing to review</EmptyTitle>
            <EmptyDescription>No proposals, no flags, nothing due for review.</EmptyDescription>
          </EmptyHeader>
        </Empty>
      </template>
    </SectionCard>
    <MemoryGroup
      v-for="[group, rows] in groups"
      :key="group"
      :group="group"
      :title="GROUPS[group][0]"
      :hint="GROUPS[group][1](sizeOf(rows))"
      :rows="rows"
      :others="active"
      :hashed="hashed"
      @changed="refresh()"
    />
    <MemoryHistory :retired="memory.retired" :active="active" />
  </div>
  <ReadState v-else shape="list" what="the memory" :failed="failed" @retry="void refresh()" />
</template>
