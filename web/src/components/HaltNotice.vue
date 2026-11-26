<script setup lang="ts">
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, inject, ref, watch } from 'vue'
import { act, ask } from '../lib/actions'
import { hourMinute } from '../lib/format'
import { BOARD } from '../lib/live'
import { perform } from '../lib/notice'
import { readAgain } from '../lib/queries'
import { keys } from '../lib/queryKeys'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { Alert, AlertAction, AlertDescription, AlertTitle } from '@/components/ui/alert'

// Every agent is stopped (code-factory halt, or Stop every agent): nothing starts until resumed. Read
// again whenever the board changes.
const live = inject(BOARD)
const busy = ref(false)
const client = useQueryClient()

// A read the board does not answer leaves the notice as it was, until the board next changes.
const halt = useQuery({
  queryKey: keys.halt,
  queryFn: ({ signal }) => ask<{ halted_at: number | null }>('/api/agents', signal),
})
const haltedAt = computed(() => halt.data.value?.halted_at ?? null)
const load = () => readAgain(client, keys.halt, halt)

async function resume(): Promise<void> {
  busy.value = true
  await perform(
    () => act('POST', '/api/agents/resume'),
    async () => {
      await Promise.all([load(), live?.refresh({ force: true })])
    },
  )
  busy.value = false
}

watch(
  () => live?.board.value,
  () => void load(),
)
</script>

<template>
  <div class="shrink-0">
    <Alert
      v-if="haltedAt !== null"
      data-holds-bottom
      role="region"
      aria-labelledby="halt-notice-heading"
      class="mt-3"
    >
      <AlertTitle id="halt-notice-heading">Agents are stopped</AlertTitle>
      <AlertDescription>
        Stopped at {{ hourMinute(haltedAt) }}. Nothing starts until you resume.
      </AlertDescription>
      <AlertAction>
        <Button type="button" variant="secondary" size="sm" :disabled="busy" @click="resume()">
          <Spinner v-if="busy" data-icon="inline-start" />Resume agents
        </Button>
      </AlertAction>
    </Alert>
  </div>
</template>
