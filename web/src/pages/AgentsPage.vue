<script setup lang="ts">
import { BotIcon, PlusSignIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { computed, shallowRef, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import AgentCard from '../components/AgentCard.vue'
import ClaudeAgentsSection from '../components/ClaudeAgentsSection.vue'
import ConnectionsSection from '../components/ConnectionsSection.vue'
import SectionCard from '../components/SectionCard.vue'
import { ItemGroup } from '@/components/ui/item'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import PageNav from '../components/PageNav.vue'
import ReadState from '../components/ReadState.vue'
import RunOrderSection from '../components/RunOrderSection.vue'
import ScorersSection from '../components/ScorersSection.vue'
import type { ClaudeAgent } from '../generated/ClaudeAgent'
import type { Unread } from '../generated/Unread'
import type { Scorer } from '../lib/scorers'
import {
  modelsByConnection,
  needsAttention,
  reachOf,
  runsHere,
  type ConnectionList,
  type ConnectionStatus,
} from '../lib/connections'
import { ask } from '../lib/actions'
import { latest } from '../lib/latest'
import { usePaged } from '../lib/paging'
import { refusalText, undone, useAction } from '../lib/notice'
import { readAgain, useApplied, usePolledRead } from '../lib/queries'
import { keys, POLL } from '../lib/queryKeys'
import { useQueryClient } from '@tanstack/vue-query'
import { FieldError } from '@/components/ui/field'
import { bodyOf, byAttention, changesOf, type AgentDraft, type AgentList } from '../lib/roster'
import { Button } from '@/components/ui/button'
import LocalHarnesses from '../components/LocalHarnesses.vue'
import AgentsTabs from '../components/AgentsTabs.vue'

// The agents and the connections defined on this machine, added, changed and removed in place;
// the agents are read again every 3 seconds, a change of what one is doing said in the status
// region; the connections are checked when the page opens and on Check, the cards keeping the
// order of the last finished check while one runs, so a pressed Check does not move away. Only
// the latest check applies its answer; a refused one says why and leaves the last answer shown.
// A first read of the agents the board refuses says why in place of the page.

// Two tabs (CF-1208): what runs (the agents and Claude Code's) and where it runs (connections).
const route = useRoute()
const onConnections = computed(() => route.query.tab === 'connections')

const list = shallowRef<AgentList | null>(null)
const connections = shallowRef<ConnectionList | null>(null)
const read = computed(() => (onConnections.value ? connections.value : list.value))
const status = shallowRef<ConnectionStatus | null>(null)
const checking = ref(false)
const checkRefusal = ref('')
const checkFailed = computed(() => `The connection check failed: ${checkRefusal.value}`)
const checks = latest()
const listRefusal = ref('')
const connectionsRefusal = ref('')
const claude = shallowRef<{ agents: ClaudeAgent[]; unread: Unread[] } | null>(null)
const scorers = shallowRef<Scorer[]>([])
const said = ref('')
const now = ref(Date.now() / 1000)
const adding = ref(false)
const { busy: addBusy, error: addError, send } = useAction()
const names = computed(() => connections.value?.connections.map((c) => c.name) ?? [])
const models = computed(() => (status.value ? modelsByConnection(status.value) : {}))
// CF-480: the order cards had when the pointer entered the grid or focus moved into it, kept
// until both leave so no card moves under the owner's pointer; null while nothing holds it.
const held = ref<string[] | null>(null)
const pointing = ref(false)
const focused = ref(false)
function hold(by: 'pointer' | 'focus', on: boolean): void {
  if (!held.value && on) held.value = cards.value.map((agent) => agent.name)
  if (by === 'pointer') pointing.value = on
  else focused.value = on
  if (!pointing.value && !focused.value) held.value = null
}
const focusLeft = (event: FocusEvent): void => {
  hold('focus', (event.currentTarget as Element).contains(event.relatedTarget as Node))
}
const cards = computed(() => {
  const read = list.value
  if (!read) return []
  const unreachable = (name: string) => {
    const agent = read.agents.find((a) => a.name === name)
    return !!agent && needsAttention(reachOf(agent, connections.value, status.value))
  }
  const ranked = byAttention(read, unreachable)
  const kept = held.value
  if (!kept) return ranked
  // An agent added while the order is held has no place in it yet and goes last.
  const place = (name: string) => (kept.includes(name) ? kept.indexOf(name) : kept.length)
  return [...ranked].sort((a, b) => place(a.name) - place(b.name))
})

const paged = usePaged(() => (list.value ? cards.value : null), 'agents_')

const agents = usePolledRead(
  keys.agents,
  (signal) => ask<AgentList>('/api/agent-definitions', signal),
  POLL.agents,
)
watch(agents.query.errorUpdatedAt, () => {
  if (agents.query.error.value) listRefusal.value = refusalText(agents.query.error.value)
})
watch(
  agents.data,
  (read) => {
    if (!read) return
    listRefusal.value = ''
    const changes = list.value ? changesOf(list.value, read) : ''
    if (changes) said.value = changes
    list.value = read
    now.value = Date.now() / 1000
  },
  { immediate: true },
)

// A read the board does not answer leaves what the page showed, until the next change reads again;
// before a first answer the tab says why and offers to read again.
const connectionsRead = useApplied<ConnectionList>(keys.connections, '/api/connections', (read) => {
  connections.value = read
  connectionsRefusal.value = ''
})
watch(connectionsRead.errorUpdatedAt, () => {
  if (connectionsRead.error.value)
    connectionsRefusal.value = refusalText(connectionsRead.error.value)
})
// The first check runs once the connections are first read, answered or not.
watch(
  connectionsRead.isPending,
  (pending) => {
    if (!pending) void check()
  },
  { immediate: true },
)

const claudeRead = useApplied<NonNullable<typeof claude.value>>(
  keys.claudeAgents,
  '/api/claude-agents',
  (read) => (claude.value = read),
)
const scorersRead = useApplied<{ scorers?: Scorer[] }>(keys.scorers, '/api/scorers', (read) => {
  if (Array.isArray(read.scorers)) scorers.value = read.scorers
})

const client = useQueryClient()
async function readConnections(): Promise<void> {
  await readAgain(client, keys.connections, connectionsRead)
}

async function refresh(): Promise<void> {
  await Promise.all([
    agents.refresh(),
    readConnections(),
    readAgain(client, keys.claudeAgents, claudeRead),
    readAgain(client, keys.scorers, scorersRead),
  ])
}

async function check(): Promise<void> {
  const current = checks.take()
  checking.value = true
  checkRefusal.value = ''
  try {
    const read = await ask<ConnectionStatus>('/api/connection-status')
    if (current()) status.value = read
  } catch (error_) {
    if (current()) checkRefusal.value = refusalText(error_)
  } finally {
    if (current()) checking.value = false
  }
}

async function changed(): Promise<void> {
  await refresh()
  await check()
}
watch(undone, () => void changed())

function open(): void {
  addError.value = ''
  adding.value = true
}

async function add(draft: AgentDraft): Promise<void> {
  await send('POST', '/api/agent-definitions', bodyOf(draft), async () => {
    adding.value = false
    await refresh()
  })
}
</script>

<template>
  <Teleport to="#header-controls">
    <AgentsTabs :connections="onConnections" />
    <Button v-if="!onConnections && list" type="button" @click="open()">
      <HugeiconsIcon :icon="PlusSignIcon" data-icon="inline-start" aria-hidden="true" />New agent
    </Button>
  </Teleport>
  <output aria-label="Agent activity" aria-live="polite" class="sr-only">{{ said }}</output>
  <div v-if="read" class="page-wide grid grid-cols-1 gap-6">
    <FieldError v-if="list?.problem" key="problem">{{ list.problem }}</FieldError>
    <FieldError v-if="checkRefusal" key="check">{{ checkFailed }}</FieldError>
    <LocalHarnesses
      v-if="!onConnections && list"
      v-model:adding="adding"
      :list="list"
      :connections="connections?.connections ?? []"
      :models="models"
      :busy="addBusy"
      :error="addError"
      @prepare="open()"
      @save="add($event)"
    />
    <SectionCard
      v-if="!onConnections && list"
      key="agents"
      heading="agents-heading"
      title="Agents"
      :count="list.agents.length"
      :description="
        list.starting
          ? ''
          : 'Agents start only by hand: no repository sets [agents] slots in .code-factory/config.toml.'
      "
      :empty="!list.agents.length"
    >
      <template #empty>
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon"
              ><HugeiconsIcon :icon="BotIcon" aria-hidden="true"
            /></EmptyMedia>
            <EmptyTitle>No agents defined</EmptyTitle>
            <EmptyDescription
              >Every run uses the default agent, each repository's harness and
              model.</EmptyDescription
            >
          </EmptyHeader>
        </Empty>
      </template>
      <template v-if="list.agents.length">
        <ItemGroup
          aria-label="Agents"
          class="grid gap-4 md:grid-cols-2"
          @pointerenter="hold('pointer', true)"
          @pointerleave="hold('pointer', false)"
          @focusin="hold('focus', true)"
          @focusout="focusLeft($event)"
        >
          <template v-for="agent in paged.rows.value" :key="agent.name">
            <AgentCard
              :agent="agent"
              :doing="list.doing[agent.name]"
              :last="list.last[agent.name]"
              :model-check="list.checks[agent.name]"
              :local="runsHere(agent, connections)"
              :now="now"
              :runtimes="list.runtimes"
              :gaps="list.gaps"
              :roles="list.roles"
              :connections="names"
              :models="models"
              :reach="reachOf(agent, connections, status, checking)"
              :checking="checking"
              @changed="refresh()"
              @check="check()"
            />
          </template>
        </ItemGroup>
        <PageNav
          label="agents"
          prefix="agents_"
          :total="paged.total.value"
          :page="paged.page.value"
          :size="paged.size.value"
        />
        <p class="text-muted-foreground mt-2 text-sm">
          A column with no agent runs each repository's default harness and model.
        </p>
      </template>
    </SectionCard>
    <ScorersSection v-if="!onConnections && scorers.length" :scorers="scorers" />
    <RunOrderSection
      v-if="!onConnections && list?.agents.length"
      :list="list"
      @changed="refresh()"
    />
    <ClaudeAgentsSection
      v-if="!onConnections && claude"
      :agents="claude.agents"
      :unread="claude.unread"
    />
    <ConnectionsSection
      v-if="onConnections && connections"
      :list="connections"
      :status="status"
      :checking="checking"
      @changed="changed()"
      @check="check()"
    />
  </div>
  <ReadState
    v-else
    :key="onConnections ? 'connections' : 'agents'"
    :shape="onConnections ? 'table' : 'cards'"
    :what="onConnections ? 'the connections' : 'the agents'"
    :failed="onConnections ? connectionsRefusal : listRefusal"
    @retry="void (onConnections ? readConnections() : agents.refresh())"
  />
</template>
