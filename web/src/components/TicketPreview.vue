<script setup lang="ts">
import SectionCard from './SectionCard.vue'
import { computed, ref } from 'vue'
import { act, readJson } from '../lib/actions'
import { perform } from '../lib/notice'
import { usePolledRead } from '../lib/queries'
import { keys, POLL } from '../lib/queryKeys'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'

// A ticket's live preview (CF-1379): drawn only while the repository sets `[preview] command`.
// The board stops it on a merge and after its idle time, so the page reads it while it is open.
const { repository, id } = defineProps<{ repository: string; id: string }>()

interface PreviewState {
  configured: boolean
  running: boolean
  port: number | null
  address: string | null
  idle_seconds: number
}

const busy = ref(false)
const path = computed(
  () => `/api/tickets/${encodeURIComponent(repository)}/${encodeURIComponent(id)}/preview`,
)
// A refusal reads as no preview; a read the board does not answer leaves the last one.
const preview = usePolledRead(
  () => keys.preview(path.value),
  (signal) => readJson<PreviewState>(path.value, signal),
  POLL.preview,
)
const state = preview.data
// The board names the address: another host than the page's, so the browser sends the board's
// cookie nowhere near the preview (CF-1426).
const address = computed(() => state.value?.address ?? '')
const minutes = computed(() => Math.max(1, Math.round((state.value?.idle_seconds ?? 0) / 60)))

async function change(method: 'POST' | 'DELETE'): Promise<void> {
  busy.value = true
  await perform(() => act(method, path.value), preview.refresh)
  busy.value = false
}
</script>

<template>
  <SectionCard
    v-if="state?.configured"
    id="preview"
    class="px-6 py-6"
    heading="preview-heading"
    title="Preview"
    :description="`stops on a merge or after ${String(minutes)} min`"
  >
    <div class="flex flex-wrap items-center gap-3">
      <template v-if="state.running">
        <Button as-child target="_blank" rel="noopener noreferrer"
          ><a :href="address"> Open preview </a></Button
        >
        <span class="font-mono text-sm text-muted-foreground">{{ address }}</span>
        <Button type="button" variant="secondary" :disabled="busy" @click="change('DELETE')"
          ><Spinner v-if="busy" data-icon="inline-start" />Stop</Button
        >
      </template>
      <Button v-else type="button" variant="secondary" :disabled="busy" @click="change('POST')"
        ><Spinner v-if="busy" data-icon="inline-start" />Preview</Button
      >
    </div>
  </SectionCard>
</template>
