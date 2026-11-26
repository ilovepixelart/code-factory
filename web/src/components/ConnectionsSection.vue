<script setup lang="ts">
import ContentCard from './ContentCard.vue'
import SectionCard from './SectionCard.vue'
import { Link01Icon, PlusSignIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { computed, ref } from 'vue'
import {
  connectionBodyOf,
  connectionDraftOf,
  kindLabel,
  sameServer,
  type ConnectionDraft,
  type ConnectionList,
  type ConnectionStatus,
  type FoundServer,
} from '../lib/connections'
import { useAction } from '../lib/notice'
import { usePaged } from '../lib/paging'
import ConnectionForm from './ConnectionForm.vue'
import ConnectionRow from './ConnectionRow.vue'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import ModelList from './ModelList.vue'
import PageNav from './PageNav.vue'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { FieldError } from '@/components/ui/field'
import { Item, ItemContent, ItemDescription, ItemGroup, ItemTitle } from '@/components/ui/item'

// The connections defined on this machine with whether each answers, and, in a section of its own
// beside them, the model servers found on this machine's default ports. `status` is the last finished check's answer, null before one
// answers; `checking` while the board checks them.
const props = defineProps<{
  list: ConnectionList
  status: ConnectionStatus | null
  checking: boolean
}>()
const emit = defineEmits<{ changed: []; check: [] }>()

const adding = ref<ConnectionDraft | null>(null)
const { busy, error, send } = useAction()
const checked = (name: string) => props.status?.connections.find((c) => c.name === name) ?? null
const found = computed(() =>
  (props.status?.local ?? []).filter(
    (server) => !props.list.connections.some((c) => sameServer(c.base_url, server.base_url)),
  ),
)
const connections = usePaged(() => props.list.connections, 'connections_')
const servers = usePaged(() => found.value, 'found_', 10)

function open(server: FoundServer | null = null): void {
  error.value = ''
  adding.value = server
    ? connectionDraftOf(null, server.kind, server.base_url)
    : connectionDraftOf(null)
}

async function add(draft: ConnectionDraft): Promise<void> {
  await send('POST', '/api/connections', connectionBodyOf(draft), () => {
    adding.value = null
    emit('changed')
  })
}
</script>

<template>
  <SectionCard
    heading="connections-heading"
    title="Connections"
    :count="list.connections.length"
    :empty="!list.connections.length"
  >
    <template #empty
      ><Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon"
            ><HugeiconsIcon :icon="Link01Icon" aria-hidden="true"
          /></EmptyMedia>
          <EmptyTitle>No connections defined</EmptyTitle>
          <EmptyDescription>Agents run on their harness's own login.</EmptyDescription>
        </EmptyHeader>
      </Empty></template
    >
    <template #action
      ><Button type="button" variant="secondary" :disabled="checking" @click="emit('check')">
        <Spinner v-if="checking" data-icon="inline-start" />Check
      </Button></template
    >

    <Teleport to="#header-controls">
      <Button type="button" @click="open()">
        <HugeiconsIcon :icon="PlusSignIcon" data-icon="inline-start" aria-hidden="true" />New
        connection
      </Button>
    </Teleport>
    <FieldError v-if="list.problem" class="mb-2">{{ list.problem }}</FieldError>
    <ConnectionForm
      v-if="adding"
      :key="`${adding.kind} ${adding.base_url}`"
      class="mb-3"
      name="New connection"
      :start="adding"
      :kinds="list.kinds"
      submit="Add"
      :error="error"
      :busy="busy"
      @save="add($event)"
      @cancel="adding = null"
    />
    <template v-if="list.connections.length">
      <ItemGroup class="gap-3" aria-label="Connections">
        <template v-for="connection in connections.rows.value" :key="connection.name">
          <ConnectionRow
            :connection="connection"
            :kinds="list.kinds"
            :status="checked(connection.name)"
            :checking="checking"
            @changed="emit('changed')"
          />
        </template>
      </ItemGroup>
      <PageNav
        label="connections"
        prefix="connections_"
        :total="connections.total.value"
        :page="connections.page.value"
        :size="connections.size.value"
      />
      <p class="text-muted-foreground mt-2 text-sm">
        Keys are read from the named environment variables when a run starts; the board stores none.
      </p>
    </template>
  </SectionCard>
  <SectionCard
    v-if="found.length"
    heading="found-heading"
    title="Found on this machine"
    :count="found.length"
  >
    <ItemGroup class="gap-3" aria-label="Found servers">
      <template v-for="server in servers.rows.value" :key="server.base_url">
        <ContentCard role="listitem" :aria-label="kindLabel(list.kinds, server.kind)">
          <Item class="py-3">
            <ItemContent class="min-w-0">
              <div data-found-title class="flex flex-wrap items-center gap-x-3 gap-y-1">
                <ItemTitle>{{ kindLabel(list.kinds, server.kind) }}</ItemTitle>
                <Button type="button" variant="secondary" @click="open(server)">
                  Add <span class="sr-only">{{ kindLabel(list.kinds, server.kind) }}</span>
                </Button>
              </div>
              <ItemDescription class="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span class="font-mono">{{ server.base_url }}</span>
                <span v-if="server.state !== 'answers'" class="text-foreground">{{
                  server.state
                }}</span>
              </ItemDescription>
              <ModelList :models="server.models" />
            </ItemContent>
          </Item>
        </ContentCard>
      </template>
    </ItemGroup>
    <PageNav
      label="found servers"
      prefix="found_"
      :fallback="10"
      :total="servers.total.value"
      :page="servers.page.value"
      :size="servers.size.value"
    />
  </SectionCard>
</template>
