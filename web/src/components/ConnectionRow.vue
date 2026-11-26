<script setup lang="ts">
import ContentCard from './ContentCard.vue'
import { Badge } from '@/components/ui/badge'
import { computed, ref } from 'vue'
import {
  connectionBodyOf,
  connectionDraftOf,
  kindLabel,
  type Checked,
  type ConnectionDraft,
  type Kind,
  type ListedConnection,
} from '../lib/connections'
import { confirm } from '../lib/confirm'
import { useAction } from '../lib/notice'
import ConnectionForm from './ConnectionForm.vue'
import CutText from './CutText.vue'
import ModelList from './ModelList.vue'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { FieldError } from '@/components/ui/field'
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemFooter,
  ItemTitle,
} from '@/components/ui/item'

// One defined connection: where it points, its key variable, whether it answers and its models;
// Edit opens its form in place, Remove takes it out. `status` is the last finished check's, null
// before one answers; `checking` while it is being checked.
const props = defineProps<{
  connection: ListedConnection
  kinds: Kind[]
  status: Checked | null
  checking: boolean
}>()
const emit = defineEmits<{ changed: [] }>()

// A connection of the owner's codex login is not asked: its status is whether the login file serves.
const usesLogin = computed(
  () => props.kinds.find((k) => k.kind === props.connection.kind)?.key === 'login',
)
// A key variable holding no value is said on the key line; its check says nothing else, as the
// board asks nothing without the key.
const keyMissing = computed(() => Boolean(props.connection.key_env) && !props.connection.key_set)

const editing = ref(false)
const { busy, error, send: sendTo } = useAction()
const address = computed(() => `/api/connections/${encodeURIComponent(props.connection.name)}`)

async function send(method: 'PATCH' | 'DELETE', body?: object): Promise<void> {
  await sendTo(method, address.value, body, () => {
    editing.value = false
    emit('changed')
  })
}

// Removing a connection asks first, as deleting a ticket does.
async function remove(): Promise<void> {
  if (await confirm(props.connection.name, { title: 'Remove connection', verb: 'Remove' })) {
    await send('DELETE')
  }
}

function open(): void {
  error.value = ''
  editing.value = true
}

function save(draft: ConnectionDraft): void {
  void send('PATCH', connectionBodyOf(draft))
}
</script>

<template>
  <ContentCard role="listitem" :aria-label="connection.name">
    <Item class="py-3">
      <ItemContent v-if="editing">
        <ConnectionForm
          :name="`Edit ${connection.name}`"
          :start="connectionDraftOf(connection)"
          :kinds="kinds"
          submit="Save"
          :error="error"
          :busy="busy"
          @save="save($event)"
          @cancel="editing = false"
        />
      </ItemContent>
      <template v-else>
        <ItemContent class="min-w-0 max-sm:basis-full">
          <ItemTitle><CutText class="font-mono" :text="connection.name" /></ItemTitle>
          <ItemDescription class="flex flex-wrap items-center gap-x-2 gap-y-1">
            <Badge variant="outline">{{ kindLabel(kinds, connection.kind) }}</Badge>
            <CutText class="font-mono" :text="connection.base_url" />
            <span v-if="connection.key_env"
              >key: <CutText class="font-mono" :text="connection.key_env" /><span
                v-if="connection.key_set"
              >
                set</span
              ><span v-else class="text-foreground"> not set</span></span
            >
            <span v-else>no key</span>
          </ItemDescription>
          <ModelList v-if="status" :models="status.models" />
        </ItemContent>
        <ItemActions class="flex-wrap">
          <span v-if="checking" class="text-muted-foreground">checking</span>
          <span v-else-if="status?.answers" class="text-foreground">{{
            usesLogin ? "uses this machine's codex login" : 'answers'
          }}</span>
          <span v-else-if="status && !keyMissing" class="text-destructive">{{
            status.problem
          }}</span>
          <Button type="button" variant="secondary" @click="open()">
            Edit <span class="sr-only">{{ connection.name }}</span>
          </Button>
          <Button type="button" variant="secondary" :disabled="busy" @click="void remove()">
            <Spinner v-if="busy" data-icon="inline-start" />Remove
            <span class="sr-only">{{ connection.name }}</span>
          </Button>
        </ItemActions>
        <ItemFooter v-if="error"
          ><FieldError>{{ error }}</FieldError></ItemFooter
        >
      </template>
    </Item>
  </ContentCard>
</template>
