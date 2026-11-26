<script setup lang="ts">
import { Folder01Icon, PlugSocketIcon, Rocket01Icon } from '@hugeicons/core-free-icons'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, inject, ref } from 'vue'
import { Button } from '@/components/ui/button'
import { Field, FieldError, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { ItemDescription, ItemGroup, ItemTitle } from '@/components/ui/item'
import { Progress } from '@/components/ui/progress'
import { Spinner } from '@/components/ui/spinner'
import FirstRunStep from './FirstRunStep.vue'
import SectionCard from './SectionCard.vue'
import { ask, post } from '../lib/actions'
import type { ConnectionList } from '../lib/connections'
import { NEW_TICKET } from '../lib/openTicket'
import { keys } from '../lib/queryKeys'

// An empty board's way to a working one: track a repository, connect a model, file the first
// ticket. Each step reads whether it is done from the board, so it ticks however it was done.
const client = useQueryClient()
const openNew = inject(NEW_TICKET, () => undefined)
const repositories = useQuery({
  queryKey: keys.repositories,
  queryFn: ({ signal }) => ask<string[]>('/api/repositories', signal),
})
const connections = useQuery({
  queryKey: keys.connections,
  queryFn: ({ signal }) => ask<ConnectionList>('/api/connections', signal),
})
const tracked = computed(() => (repositories.data.value ?? []).length > 0)
const connected = computed(() => (connections.data.value?.connections ?? []).length > 0)
// Filing the first ticket ends the first run, so only the first two can be done while it shows.
const stepsDone = computed(() => Number(tracked.value) + Number(connected.value))
const next = computed(() => (!tracked.value ? 'track' : !connected.value ? 'connect' : 'file'))

const path = ref('')
const refusal = ref('')
const sending = ref(false)

async function track(): Promise<void> {
  if (!path.value.trim() || sending.value) return
  sending.value = true
  refusal.value = ''
  try {
    await post('/api/repositories', { path: path.value.trim() })
    path.value = ''
    await client.invalidateQueries({ queryKey: keys.repositories })
    await client.invalidateQueries({ queryKey: keys.board })
  } catch (error) {
    refusal.value = error instanceof Error ? error.message : String(error)
  } finally {
    sending.value = false
  }
}
</script>

<template>
  <SectionCard heading="first-run-heading" title="Get started" :count="`${String(stepsDone)} of 3`">
    <template #toolbar>
      <Progress
        :model-value="(stepsDone / 3) * 100"
        :get-value-text="() => `${String(stepsDone)} of 3 steps complete`"
        aria-label="Setup progress"
      />
    </template>
    <ItemGroup class="gap-3" aria-label="Steps to get started">
      <FirstRunStep step="track" :done="tracked" :current="next === 'track'" :icon="Folder01Icon">
        <ItemTitle>Track a repository</ItemTitle>
        <ItemDescription v-if="tracked">{{ repositories.data.value?.join(', ') }}</ItemDescription>
        <form v-else class="mt-2 grid max-w-lg gap-4" @submit.prevent="track()">
          <Field :data-invalid="refusal ? true : undefined">
            <FieldLabel for="first-repository">Repository folder</FieldLabel>
            <Input
              id="first-repository"
              :model-value="path"
              placeholder="/Users/you/src/app"
              autocomplete="off"
              :aria-invalid="refusal ? true : undefined"
              :aria-describedby="refusal ? 'first-repository-error' : undefined"
              @update:model-value="path = String($event)"
            />
            <FieldError v-if="refusal" id="first-repository-error">{{ refusal }}</FieldError>
          </Field>
          <Button class="justify-self-start" type="submit" :disabled="sending || !path.trim()">
            <Spinner v-if="sending" data-icon="inline-start" />Track
          </Button>
        </form>
      </FirstRunStep>
      <FirstRunStep
        step="connect"
        :done="connected"
        :current="next === 'connect'"
        :icon="PlugSocketIcon"
      >
        <ItemTitle>Connect a model</ItemTitle>
        <ItemDescription>Set up a connection if your agent needs a model server.</ItemDescription>
        <Button
          v-if="!connected"
          :variant="next === 'connect' ? 'default' : 'secondary'"
          class="mt-2 self-start"
          as-child
        >
          <RouterLink :to="{ path: '/agents', query: { tab: 'connections' } }"
            >Open Connections</RouterLink
          >
        </Button>
      </FirstRunStep>
      <FirstRunStep step="file" :done="false" :current="next === 'file'" :icon="Rocket01Icon">
        <ItemTitle>File your first ticket</ItemTitle>
        <ItemDescription v-if="!tracked">Track a repository to create a ticket.</ItemDescription>
        <Button
          type="button"
          :variant="next === 'file' ? 'default' : 'secondary'"
          class="mt-2 self-start"
          :disabled="!tracked"
          @click="openNew()"
          >New ticket</Button
        >
      </FirstRunStep>
    </ItemGroup>
  </SectionCard>
</template>
