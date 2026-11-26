<script setup lang="ts">
import { Search01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import type Fuse from 'fuse.js'
import { computed, inject, shallowRef, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { refDebounced } from '@vueuse/core'
import { useQuery } from '@tanstack/vue-query'
import { act, ask } from '../lib/actions'
import type { PagedArchive } from '../lib/memory'
import { keys } from '../lib/queryKeys'
import { UPDATED } from '../lib/build'
import { STAGES, type Card } from '../lib/board'
import { BOARD } from '../lib/live'
import { failed, perform } from '../lib/notice'
import { NEW_TICKET, panelTicket } from '../lib/openTicket'
import { settled, useOverlay } from '../lib/overlayHistory'
import { keysOf } from '../lib/shortcuts'
import { AGENT_STAGES, ticketHref } from '../lib/ticket'
import { setArchived, startAgent, ticketPath } from '../lib/ticketActions'
import { PAGES } from '../router'
import { Empty, EmptyDescription, EmptyHeader } from '@/components/ui/empty'
import { useSavedViews, viewUrl } from '../lib/savedViews'
import { ListboxFilter } from 'reka-ui'
import {
  CommandDialog,
  CommandGroup,
  CommandItem,
  CommandList,
  CommandShortcut,
} from '@/components/ui/command'
import { InputGroup, InputGroupAddon } from '@/components/ui/input-group'
import { Kbd, KbdGroup } from '@/components/ui/kbd'

interface Result {
  key: string
  label: string
  hint: string
  /** The shortcut that does the same, from the shortcut sheet. */
  keys?: string[]
  to?: string
  /** A change to send before going to `to`. */
  post?: string
  /** What the entry does in place, instead of going anywhere. */
  run?: () => Promise<void> | void
}

// The agent commands: each sends its change, then shows the board.
const AGENT_COMMANDS: Result[] = [
  {
    key: 'agents-stop',
    label: 'Stop every agent',
    hint: 'agent',
    to: '/tickets',
    post: '/api/agents/stop',
  },
  {
    key: 'agents-resume',
    label: 'Resume agents',
    hint: 'agent',
    to: '/tickets',
    post: '/api/agents/resume',
  },
]

const router = useRouter()
const route = useRoute()
const live = inject(BOARD)
const openNew = inject(NEW_TICKET, () => undefined)
const shown = useOverlay()
const query = ref('')
const { views, refresh: refreshViews } = useSavedViews()

// Archived and released tickets, from the Archive page's own search, once the query is two
// characters long and has rested; each says how it left the board.
const ARCHIVED_MOST = 5
const typedQuery = computed(() => query.value.trim())
const restingQuery = refDebounced(typedQuery, 250)
const archiveAddress = computed(() => {
  const asked = { q: restingQuery.value, page: '1', size: String(ARCHIVED_MOST) }
  return `/api/archive?${new URLSearchParams(asked).toString()}`
})
const archiveRead = useQuery({
  queryKey: computed(() => keys.archive(archiveAddress.value)),
  queryFn: ({ signal }) => ask<PagedArchive>(archiveAddress.value, signal),
  enabled: computed(() => shown.value && restingQuery.value.length >= 2),
})
const archived = computed<Result[]>(() =>
  shown.value && typedQuery.value.length >= 2
    ? (archiveRead.data.value?.rows ?? []).map((row) => ({
        key: `archived:${row.repository}/${row.id}`,
        label: `${row.id} ${row.title}`,
        hint: row.stage === 'released' ? `Released ${row.release}` : 'Archived',
        to: ticketHref(row.repository, row.id),
      }))
    : [],
)

const tickets = computed<Result[]>(() =>
  STAGES.flatMap((s) => live?.board.value?.columns[s] ?? []).map((c) => ({
    key: `${c.repository}/${c.id}`,
    label: `${c.id} ${c.title}`,
    hint: c.repository,
    to: ticketHref(c.repository, c.id),
  })),
)

// The ticket the person has open: in the panel, else the ticket page the address names.
const openTicket = computed(() => {
  const { repository, id } = route.params
  if (panelTicket.value) return panelTicket.value
  return repository && id ? { repository: String(repository), id: String(id) } : null
})
const openCard = computed<Card | undefined>(() =>
  STAGES.flatMap((s) => live?.board.value?.columns[s] ?? []).find(
    (c) => c.repository === openTicket.value?.repository && c.id === openTicket.value.id,
  ),
)

// The entries for the open ticket, through the requests its buttons send. An agent is offered
// where the Status section's button is: in a column an agent works in, with none running.
const ticketCommands = computed<Result[]>(() => {
  const card = openCard.value
  if (!card) return []
  const base = ticketPath(card.repository, card.id)
  const done = () => live?.refresh({ force: true }) ?? Promise.resolve()
  const entries: Result[] = []
  if (AGENT_STAGES.includes(card.stage) && !card.runs.length)
    entries.push({
      key: 'ticket-start',
      label: 'Start agent',
      hint: card.id,
      keys: keysOf('ticket-start'),
      run: () => void perform(() => startAgent(base), done),
    })
  if (!card.archived)
    entries.push({
      key: 'ticket-archive',
      label: 'Archive',
      hint: card.id,
      run: () => void perform(() => setArchived(base, true), done),
    })
  return entries
})

// The open ticket's entries, then the pages and the other commands, after the tickets.
const commands = computed<Result[]>(() => [
  ...views.value.map((view) => ({
    key: `view:${view.name}`,
    label: view.name,
    hint: 'saved view',
    to: viewUrl(view),
  })),
  ...ticketCommands.value,
  { key: 'new-ticket', label: 'New ticket', hint: 'action', keys: keysOf('new'), run: openNew },
  ...PAGES.map((p) => ({
    key: p.path,
    label: `Go to ${p.name}`,
    hint: 'page',
    keys: keysOf(p.name.toLowerCase()),
    to: p.path,
  })),
  {
    key: 'agents-connections',
    label: 'Agents: Connections',
    hint: 'page',
    to: '/agents?tab=connections',
  },
  ...AGENT_COMMANDS,
])

// Token search matches each typed word against the label's words, so word order does not count,
// and 'all' keeps only entries matching every word, so another word narrows the list.
// The library loads when the menu first opens (it is not in the entry chunk); until it has, a
// typed query matches every word as a case-insensitive substring, so the list is never empty for
// text that is in a label, and it re-ranks by the fuzzy match the moment the library arrives.
const fuse = shallowRef<typeof Fuse | null>(null)
let loading: Promise<void> | null = null

function loadFuse(): Promise<void> {
  if (fuse.value) return Promise.resolve()
  loading ??= import('fuse.js').then(
    (module) => {
      fuse.value = module.default
    },
    () => {
      // A tab older than the deployed build asks for a chunk that is gone.
      loading = null
      failed(UPDATED)
    },
  )
  return loading
}

const entries = computed(() => [...tickets.value, ...commands.value])

const finder = computed(() =>
  fuse.value
    ? new fuse.value(entries.value, {
        keys: ['label'],
        useTokenSearch: true,
        tokenMatch: 'all',
        threshold: 0.4,
      })
    : null,
)

function search(needle: string): Result[] {
  if (finder.value) return finder.value.search(needle, { limit: 8 }).map((r) => r.item)
  const words = needle.toLowerCase().split(/\s+/)
  return entries.value
    .filter((e) => words.every((w) => e.label.toLowerCase().includes(w)))
    .slice(0, 8)
}

const results = computed<Result[]>(() => {
  if (!shown.value) return []
  const needle = query.value.trim()
  if (needle !== '') return search(needle)
  return [...tickets.value.slice(0, 8), ...commands.value]
})

async function open(): Promise<void> {
  query.value = ''
  shown.value = true
  void loadFuse()
  void live?.refresh()
  await refreshViews()
}

async function go(result: Result | undefined): Promise<void> {
  if (!result) return
  shown.value = false
  // The overlay's history entry is popped first: a navigation or another overlay would land on it.
  await settled()
  if (result.run) {
    await result.run()
    return
  }
  const post = result.post
  if (post)
    await perform(
      () => act('POST', post),
      () => live?.refresh({ force: true }) ?? Promise.resolve(),
    )
  if (result.to) await router.push(result.to)
}

defineExpose({ open })
</script>

<template>
  <!-- The search is the listbox's own filter on our query: the list holds the ranked results, so
       CommandInput's substring filter, which would hide fuzzy and reordered matches, is not used. -->
  <CommandDialog
    v-model:open="shown"
    title="Command menu"
    description="Jump to a ticket or a page, or run a command"
  >
    <div data-slot="command-input-wrapper" class="p-1 pb-0">
      <InputGroup class="h-8!">
        <ListboxFilter
          v-model="query"
          data-slot="command-input"
          auto-focus
          role="combobox"
          aria-label="Search commands"
          aria-controls="command-results"
          :aria-expanded="results.length > 0"
          autocomplete="off"
          placeholder="Jump to a ticket or a page"
          class="w-full text-sm outline-hidden"
        />
        <InputGroupAddon>
          <HugeiconsIcon :icon="Search01Icon" aria-hidden="true" />
        </InputGroupAddon>
        <InputGroupAddon align="inline-end"><Kbd>esc</Kbd></InputGroupAddon>
      </InputGroup>
    </div>
    <CommandList id="command-results" aria-label="Commands">
      <CommandGroup v-if="results.length" key="results">
        <CommandItem
          v-for="result in results"
          :key="result.key"
          :value="result.key"
          @select="go(result)"
        >
          <span class="min-w-0 flex-1 truncate">{{ result.label }}</span>
          <span class="text-muted-foreground">{{ result.hint }}</span>
          <CommandShortcut v-if="result.keys?.length">
            <KbdGroup
              ><Kbd v-for="key in result.keys" :key="key">{{ key }}</Kbd></KbdGroup
            ></CommandShortcut
          >
        </CommandItem>
      </CommandGroup>
      <CommandGroup v-if="archived.length" key="archived" heading="Archived" data-archived>
        <CommandItem
          v-for="result in archived"
          :key="result.key"
          :value="result.key"
          @select="go(result)"
        >
          <span class="min-w-0 flex-1 truncate">{{ result.label }}</span>
          <span class="text-muted-foreground">{{ result.hint }}</span>
        </CommandItem>
      </CommandGroup>
      <Empty v-if="!results.length && !archived.length" class="px-2.5 py-1.5">
        <EmptyHeader>
          <EmptyDescription>Nothing matches.</EmptyDescription>
        </EmptyHeader>
      </Empty>
    </CommandList>
  </CommandDialog>
</template>
